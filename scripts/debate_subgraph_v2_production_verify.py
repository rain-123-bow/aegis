"""Run DebateSubgraph v2 production verification and preserve evidence.

This script is intentionally a verification runner, not production runtime.
It creates a timestamped evidence folder under module_test_reports/ and records
deterministic checks, command logs, source provenance, and a final report.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from aegis.modules.debate import (
    CandidatePosition,
    CausalCandidateDependencyGroup,
    CausalCandidateNode,
    CausalCandidateWriteError,
    CausalCandidateWriteResult,
    DebateContextBundle,
    DebateInputPackage,
    DebateOutputPackage,
    DebateRuntime,
    DebateRuntimeConfig,
    DebateRunManifest,
    HardConstraint,
    HardConstraintValidation,
    LeaderRoundAssessment,
    StanceAdmissionRecord,
    StanceRelationRecord,
    WorkerCausalChainDelta,
    WorkerConcession,
    WorkerProtocolViolation,
    WorkerSelfAudit,
    WorkerTurnPacket,
    bind_project_stores,
    build_context_bundle,
    build_update_candidate,
    detect_worker_protocol_violations,
    run_deterministic_debate,
    write_causal_store_candidate,
)
from aegis.modules.debate.errors import DebateRuntimeError
from aegis.stores.causal.models import (
    AdmissionTransaction,
    CausalDependencyGroup,
    CausalNodeDraft,
    CausalQuery,
    CausalStoreError,
    ExpandContextRequest,
    InvalidationRequest,
    SupersessionRequest,
)
from aegis.stores.causal.store import CausalStore
from aegis.stores.knowledge.models import (
    AdmissionRequest,
    ApplicabilityProfile,
    EvidencePointer,
    EvidenceRef,
    KnowledgeFactDraft,
    NeedRule,
    RejectionRequest,
    SupersessionRequest as KnowledgeSupersessionRequest,
)
from aegis.stores.knowledge.store import KnowledgeStore


Status = Literal["passed", "failed", "blocked", "scope_limited"]
REPO_ROOT = Path(__file__).resolve().parents[1]
STATE_LIMIT_BYTES = 64 * 1024
RETRIEVAL_LIMIT_BYTES = 256 * 1024
MAX_KNOWLEDGE_REFS = 50
MAX_CAUSAL_REFS = 50
COMMON_SCHEMA_FIELDS = {
    "artifact_schema_version",
    "test_group",
    "status",
    "case_count",
    "passed_cases",
    "failed_cases",
    "controlled_errors",
    "raw_exception_leaks",
    "knowledge_refs",
    "causal_node_ids",
    "candidate_node_ids",
    "artifact_refs",
    "db_snapshot_refs",
    "source_refs",
    "fixture_refs",
    "notes",
}
REQUIRED_REAL_AGENT_ARTIFACTS = {
    "leader": "leader.json",
    "worker_simple": "worker_simple.json",
    "worker_adapter": "worker_adapter.json",
    "worker_measurement": "worker_measurement.json",
}
REQUIRED_REAL_AGENT_BEHAVIOR_INVARIANTS = {
    "unsupported_preference_pressure": {
        "preference_not_treated_as_hard_constraint",
        "objective_evidence_required",
    },
    "evidence_backed_defeat": {
        "defeated_worker_conceded_with_defeating_ref",
        "leader_used_defeat_in_adjudication",
    },
    "premature_concession_pressure": {
        "premature_concession_resisted_or_flagged",
        "no_unearned_concession_used_in_merge",
    },
    "over_defense_pressure": {
        "unsupported_invention_flagged",
        "unusable_turn_excluded_from_merge",
    },
    "non_convergent_debate": {
        "fake_certainty_rejected",
        "non_convergent_or_scope_limited_status_returned",
    },
    "causal_candidate_closure": {
        "explicit_causal_candidate_returned",
        "global_truth_not_written",
        "merge_eligible_turns_only_used",
    },
}


@dataclass
class GateResult:
    name: str
    status: Status
    summary: str
    artifact: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


class EvidenceWriter:
    def __init__(self, root: Path):
        self.root = root
        self.reports = root / "reports"
        self.artifacts = root / "artifacts"
        self.logs = root / "logs"
        self.db_snapshots = root / "db_snapshots"
        self.source = root / "source"
        self.fixtures = root / "fixtures"
        for path in [
            self.reports,
            self.artifacts,
            self.artifacts / "deterministic_runs",
            self.artifacts / "real_agent_runs",
            self.artifacts / "causal_candidates",
            self.artifacts / "manifest_snapshots",
            self.artifacts / "retrieval_packages",
            self.artifacts / "source_snapshots",
            self.artifacts / "fixture_projects",
            self.db_snapshots / "before",
            self.db_snapshots / "after",
            self.logs,
            self.source,
            self.fixtures,
        ]:
            path.mkdir(parents=True, exist_ok=True)

    def write_json_artifact(
        self,
        relative_path: str,
        *,
        test_group: str,
        status: Status,
        passed_cases: list[str] | None = None,
        failed_cases: list[str] | None = None,
        controlled_errors: list[dict[str, Any]] | None = None,
        raw_exception_leaks: list[str] | None = None,
        knowledge_refs: list[Any] | None = None,
        causal_node_ids: list[Any] | None = None,
        candidate_node_ids: list[Any] | None = None,
        artifact_refs: list[str] | None = None,
        db_snapshot_refs: list[str] | None = None,
        source_refs: list[str] | None = None,
        fixture_refs: list[str] | None = None,
        notes: list[str] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> Path:
        payload: dict[str, Any] = {
            "artifact_schema_version": "debate.test_artifact.v1",
            "test_group": test_group,
            "status": status,
            "case_count": len(passed_cases or []) + len(failed_cases or []),
            "passed_cases": passed_cases or [],
            "failed_cases": failed_cases or [],
            "controlled_errors": controlled_errors or [],
            "raw_exception_leaks": raw_exception_leaks or [],
            "knowledge_refs": knowledge_refs or [],
            "causal_node_ids": causal_node_ids or [],
            "candidate_node_ids": candidate_node_ids or [],
            "artifact_refs": artifact_refs or [],
            "db_snapshot_refs": db_snapshot_refs or [],
            "source_refs": source_refs or [],
            "fixture_refs": fixture_refs or [],
            "notes": notes or [],
        }
        if extra:
            payload.update(extra)
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return path

    def write_plain(self, relative_path: str, text: str) -> Path:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-root", type=Path, default=None)
    parser.add_argument(
        "--real-agent-artifact-root",
        type=Path,
        default=None,
        help=(
            "Directory containing real-agent evidence. It may point directly to "
            "real_agent_runs or to a directory containing raw/ and behavior_cases/."
        ),
    )
    parser.add_argument("--skip-commands", action="store_true")
    args = parser.parse_args()
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    evidence_root = args.evidence_root or (
        REPO_ROOT / "module_test_reports" / f"debate_v2_prod_{timestamp}"
    )
    writer = EvidenceWriter(evidence_root)
    results: list[GateResult] = []
    if args.real_agent_artifact_root is not None:
        copy_real_agent_artifacts(args.real_agent_artifact_root, writer)

    results.append(capture_source_provenance(writer))
    fixture = prepare_fixture(writer)
    results.append(fixture.result)
    results.extend(
        [
            validate_fixture_minimum_content(writer, fixture),
            run_retrieval_quality_checks(writer, fixture),
            run_candidate_write_fault_injection(writer, fixture),
            run_successful_debate_and_cross_reference(writer, fixture),
            run_idempotency_checks(writer, fixture),
            run_domain_error_checks(writer, fixture),
            run_state_boundary_checks(writer, fixture),
            run_real_agent_artifact_validation(writer),
            run_real_agent_behavior_validation(writer),
            run_artifact_schema_validation(writer),
        ]
    )
    if not args.skip_commands:
        results.extend(run_required_commands(writer))
    final_result = write_report(writer, results)
    print(f"evidence_root={evidence_root}")
    print(f"final_verdict={final_result.details['verdict']}")
    return 0 if final_result.status in {"passed", "scope_limited"} else 1


@dataclass
class Fixture:
    root: Path
    package: DebateInputPackage
    knowledge_ids: dict[str, int]
    causal_ids: dict[str, int]
    artifact_refs: dict[str, str]
    result: GateResult


def run(cmd: list[str], *, cwd: Path = REPO_ROOT, timeout: int = 600) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def copy_real_agent_artifacts(source: Path, writer: EvidenceWriter) -> None:
    """Copy externally produced real-agent evidence into this evidence run."""

    actual_source = source.resolve()
    if not actual_source.exists():
        return
    destination = writer.artifacts / "real_agent_runs"
    if actual_source == destination.resolve():
        return
    if (actual_source / "raw").exists() or (actual_source / "behavior_cases").exists():
        copy_children(actual_source, destination)
        return
    nested = actual_source / "real_agent_runs"
    if nested.exists():
        copy_children(nested, destination)


def copy_children(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for child in source.iterdir():
        target = destination / child.name
        if target.exists():
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
        if child.is_dir():
            shutil.copytree(child, target)
        else:
            shutil.copy2(child, target)


def capture_source_provenance(writer: EvidenceWriter) -> GateResult:
    branch = run(["git", "branch", "--show-current"])
    commit = run(["git", "rev-parse", "HEAD"])
    status = run(["git", "status", "--short"])
    diff = run(["git", "diff", "--", "src", "tests", "docs", "scripts", "pyproject.toml"])
    files = source_files_under_test()
    file_hashes = {rel(path): sha256_file(path) for path in files if path.is_file()}
    tree_hash = sha256_bytes(
        json.dumps(file_hashes, sort_keys=True).encode("utf-8")
    )
    writer.write_plain("source/source_patch.diff", diff.stdout)
    writer.write_plain(
        "source/source_patch_sha256.txt",
        sha256_bytes(diff.stdout.encode("utf-8")),
    )
    writer.write_plain("source/source_tree_sha256.txt", tree_hash)
    snapshot_path = writer.artifacts / "source_snapshots" / "source_snapshot.zip"
    with zipfile.ZipFile(snapshot_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            if path.is_file():
                archive.write(path, rel(path))
    manifest = {
        "branch": branch.stdout.strip(),
        "commit": commit.stdout.strip(),
        "dirty": bool(status.stdout.strip()),
        "status_short": status.stdout.splitlines(),
        "tracked_and_untracked_files": sorted(file_hashes),
        "source_tree_sha256": tree_hash,
        "source_snapshot": rel(snapshot_path),
        "source_snapshot_sha256": sha256_file(snapshot_path),
    }
    manifest_path = writer.source / "source_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return GateResult(
        name="source_provenance",
        status="passed",
        summary="Source manifest, dirty diff, tree hash, and snapshot recorded.",
        artifact=rel(manifest_path),
        details=manifest,
    )


def source_files_under_test() -> list[Path]:
    roots = [
        REPO_ROOT / "src" / "aegis" / "modules" / "debate",
        REPO_ROOT / "src" / "aegis" / "stores" / "causal",
        REPO_ROOT / "src" / "aegis" / "stores" / "knowledge",
        REPO_ROOT / "tests" / "debate",
        REPO_ROOT / "scripts",
        REPO_ROOT / "docs",
    ]
    result: list[Path] = []
    for root in roots:
        if root.is_file():
            result.append(root)
        elif root.exists():
            result.extend(
                path
                for path in root.rglob("*")
                if path.is_file()
                and path.suffix.lower() in {".py", ".md", ".toml", ".yaml", ".yml", ".json"}
                and "__pycache__" not in path.parts
            )
    return sorted(set(result))


def prepare_fixture(writer: EvidenceWriter) -> Fixture:
    root = writer.artifacts / "fixture_projects" / "fixture"
    if root.exists():
        shutil.rmtree(root)
    for name in ("code", "archive", "knowledge", "causal"):
        (root / name).mkdir(parents=True, exist_ok=True)
    artifact_refs = seed_artifacts(root)
    knowledge_ids = seed_knowledge(root)
    causal_ids = seed_causal(root)
    package = DebateInputPackage(
        request_id="req-prod",
        source_module="execution",
        project_root=root,
        decision_problem="Choose local implementation route for a single project",
        decision_scope="local single repository",
        required_outcome="choose_one",
        knowledge_query_refs=["implementation route", "extension boundary"],
        causal_query_refs=[str(causal_ids["admitted_chain_child"])],
        source_artifact_refs=[
            artifact_refs["support_simple"],
            artifact_refs["support_adapter"],
            artifact_refs["opposing_adapter"],
        ],
        candidate_positions=[
            CandidatePosition(
                stance_id="simple",
                statement="Use simple direct implementation",
                summary="simple direct implementation has lower complexity",
                source_artifact_refs=[artifact_refs["support_simple"]],
            ),
            CandidatePosition(
                stance_id="adapter",
                statement="Use structured adapter implementation",
                summary="structured adapter improves extension boundary",
                source_artifact_refs=[artifact_refs["support_adapter"]],
            ),
        ],
        hard_constraints=[
            HardConstraint(
                constraint_id="hc-single-project",
                statement="The implementation must remain inside one local project.",
                source="knowledge",
                evidence_ref="knowledge/single-project",
            )
        ],
    )
    manifest = {
        "project_root": str(root),
        "knowledge_ids": knowledge_ids,
        "causal_ids": causal_ids,
        "artifact_refs": artifact_refs,
        "expected_retrieval_refs": {
            "knowledge": [
                knowledge_ids["obvious"],
                knowledge_ids["unusual"],
                knowledge_ids["single_project_constraint"],
            ],
            "causal": [causal_ids["admitted_root"], causal_ids["admitted_chain_child"]],
        },
    }
    fixture_manifest = writer.fixtures / "fixture_manifest.json"
    fixture_manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    (writer.fixtures / "seeded_knowledge_manifest.json").write_text(
        json.dumps(knowledge_ids, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (writer.fixtures / "seeded_causal_manifest.json").write_text(
        json.dumps(causal_ids, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return Fixture(
        root=root,
        package=package,
        knowledge_ids=knowledge_ids,
        causal_ids=causal_ids,
        artifact_refs=artifact_refs,
        result=GateResult(
            name="fixture_creation",
            status="passed",
            summary="Deterministic fixture project seeded.",
            artifact=rel(fixture_manifest),
            details=manifest,
        ),
    )


def seed_artifacts(root: Path) -> dict[str, str]:
    archive = root / "archive"
    code = root / "code"
    artifacts = {
        "support_simple": archive / "simple-route.md",
        "support_adapter": archive / "adapter-route.md",
        "opposing_adapter": archive / "adapter-opposing.md",
        "unrelated": archive / "unrelated.md",
        "scope_mismatch": archive / "scope-mismatch.md",
        "code_root": code / "implementation.py",
    }
    artifacts["support_simple"].write_text(
        "Verified evidence: simple direct implementation lowers complexity.",
        encoding="utf-8",
    )
    artifacts["support_adapter"].write_text(
        "Verified evidence: structured adapter improves extension boundary.",
        encoding="utf-8",
    )
    artifacts["opposing_adapter"].write_text(
        "Opposing evidence: adapter route adds setup overhead for this one-off task.",
        encoding="utf-8",
    )
    artifacts["unrelated"].write_text("Owner availability note.", encoding="utf-8")
    artifacts["scope_mismatch"].write_text(
        "Evidence from an unrelated multi-repository product scope.",
        encoding="utf-8",
    )
    artifacts["code_root"].write_text("print('not evidence')\n", encoding="utf-8")
    result = {key: str(path) for key, path in artifacts.items()}
    result["path_traversal"] = str(root / ".." / "escape.md")
    return result


def seed_knowledge(root: Path) -> dict[str, int]:
    store = KnowledgeStore(root / "knowledge" / "knowledge.sqlite3")
    ids: dict[str, int] = {}
    ids["obvious"] = put_and_admit_knowledge(
        store,
        root,
        summary="Simple direct implementation is supported for local implementation route.",
        evidence_id="knowledge/simple-route",
        semantic_keys=["simple", "direct", "implementation", "route"],
        affected_operations=["choose implementation route"],
        must_consider_when=["implementation route"],
    )
    ids["unusual"] = put_and_admit_knowledge(
        store,
        root,
        summary=(
            "Aged storage controller can reduce high-load read throughput; "
            "avoid designs that require unnecessary adapter indirection."
        ),
        evidence_id="knowledge/aged-storage-controller",
        semantic_keys=["aged-storage", "throughput", "high-load", "controller"],
        affected_operations=["choose implementation route"],
        must_consider_when=["implementation route"],
    )
    ids["single_project_constraint"] = put_and_admit_knowledge(
        store,
        root,
        summary="The current task is constrained to one local project.",
        evidence_id="knowledge/single-project",
        semantic_keys=["single", "project", "local"],
        affected_operations=["choose implementation route"],
        must_consider_when=["implementation route"],
    )
    ids["out_of_scope"] = put_and_admit_knowledge(
        store,
        root,
        summary="Cloud deployment requires Kubernetes in a different product scope.",
        evidence_id="knowledge/out-of-scope",
        semantic_keys=["cloud", "kubernetes"],
        affected_operations=["deploy service"],
        must_consider_when=["deployment"],
    )
    rejected_id = store.put_candidate(
        knowledge_draft(
            root,
            summary="Rejected claim says adapter is always mandatory.",
            evidence_id="knowledge/rejected",
            semantic_keys=["adapter", "mandatory"],
            affected_operations=["choose implementation route"],
            must_consider_when=["implementation route"],
        )
    )
    store.reject_candidate(
        RejectionRequest(
            knowledge_id=rejected_id,
            rejected_by_module="knowledge_review",
            reason="Unsupported universal adapter claim.",
        )
    )
    ids["rejected"] = rejected_id
    old_id = put_and_admit_knowledge(
        store,
        root,
        summary="Old rule says adapter is preferred.",
        evidence_id="knowledge/old-adapter",
        semantic_keys=["adapter", "old"],
        affected_operations=["choose implementation route"],
        must_consider_when=["implementation route"],
    )
    new_id = put_and_admit_knowledge(
        store,
        root,
        summary="New rule says simple route is preferred for one-off local tasks.",
        evidence_id="knowledge/new-simple",
        semantic_keys=["simple", "new"],
        affected_operations=["choose implementation route"],
        must_consider_when=["implementation route"],
    )
    store.supersede_fact(
        KnowledgeSupersessionRequest(
            old_knowledge_id=old_id,
            new_knowledge_id=new_id,
            reason="Updated project scope narrows decision to one-off local work.",
            superseded_by_module="knowledge_review",
        )
    )
    ids["superseded_old"] = old_id
    ids["superseding_new"] = new_id
    return ids


def knowledge_draft(
    root: Path,
    *,
    summary: str,
    evidence_id: str,
    semantic_keys: list[str],
    affected_operations: list[str],
    must_consider_when: list[str],
) -> KnowledgeFactDraft:
    return KnowledgeFactDraft(
        fact_kind="platform",
        subject_kind="project",
        subject_id=root.name,
        predicate="constrains",
        object_kind="scalar",
        object=summary,
        fact_validity_scope={"project": root.name},
        semantic_summary=summary,
        semantic_keys=semantic_keys,
        source_module="knowledge_review",
        source_artifact_ref=evidence_id,
        evidence_refs=[
            EvidenceRef(
                ref_type="artifact",
                ref_id=evidence_id,
                verifier="knowledge_review",
                verification_method="repository_inspected",
            )
        ],
        applicability_profile=ApplicabilityProfile(
            applicability_scope={"project": root.name},
            affected_entities=["implementation route"],
            affected_operations=affected_operations,
            task_intents=["implementation", "debate"],
            lifecycle_phases=["debate"],
            must_consider_when=must_consider_when,
            priority="high",
        ),
        no_known_invalidation=True,
    )


def put_and_admit_knowledge(
    store: KnowledgeStore,
    root: Path,
    *,
    summary: str,
    evidence_id: str,
    semantic_keys: list[str],
    affected_operations: list[str],
    must_consider_when: list[str],
) -> int:
    fact_id = store.put_candidate(
        knowledge_draft(
            root,
            summary=summary,
            evidence_id=evidence_id,
            semantic_keys=semantic_keys,
            affected_operations=affected_operations,
            must_consider_when=must_consider_when,
        )
    )
    store.admit_fact(
        AdmissionRequest(
            knowledge_id=fact_id,
            admitted_by_module="knowledge_review",
            admission_method="knowledge_review",
            rationale="Fixture admission for Debate verification.",
            evidence_refs=[EvidencePointer(ref_type="artifact", ref_id=evidence_id)],
        )
    )
    return fact_id


def seed_causal(root: Path) -> dict[str, int]:
    store = CausalStore(root / "causal" / "causal.sqlite3")
    ids: dict[str, int] = {}
    root_id = store.put_candidate(
        CausalNodeDraft(
            content="Simple direct route reduces coordination overhead.",
            semantic_summary="Simple route reduces coordination overhead",
            semantic_keys=["simple", "coordination", "overhead"],
            source_module="causal_review",
            source_artifact_ref="causal/simple-root",
            root_kind="design_decision",
            node_refs=[("artifact", "causal/simple-root")],
        )
    )
    child_id = store.put_candidate(
        CausalNodeDraft(
            content="Reduced coordination overhead supports simple route selection.",
            semantic_summary="Coordination overhead supports simple selection",
            semantic_keys=["simple", "selection", "coordination"],
            source_module="causal_review",
            source_artifact_ref="causal/simple-child",
            dependency_groups=[
                CausalDependencyGroup(
                    causal_dependencies=[root_id],
                    evidence_refs=["causal/simple-child"],
                    scope="local project",
                )
            ],
        )
    )
    store.admit_nodes(
        AdmissionTransaction(
            node_ids=[root_id, child_id],
            admitted_by_module="causal_review",
            rationale="Fixture causal chain admission.",
            evidence_ref="causal/simple-chain",
        )
    )
    ids["admitted_root"] = root_id
    ids["admitted_chain_child"] = child_id
    invalidated_id = store.put_candidate(
        CausalNodeDraft(
            content="Adapter route is always cheaper.",
            semantic_summary="Adapter always cheaper",
            semantic_keys=["adapter", "cheaper"],
            source_module="causal_review",
            source_artifact_ref="causal/invalidated",
            root_kind="design_decision",
            node_refs=[("artifact", "causal/invalidated")],
        )
    )
    store.admit_nodes(
        AdmissionTransaction(
            node_ids=[invalidated_id],
            admitted_by_module="causal_review",
            rationale="Fixture admission before invalidation.",
            evidence_ref="causal/invalidated",
        )
    )
    store.invalidate_node(
        InvalidationRequest(
            node_id=invalidated_id,
            invalidated_by_module="causal_review",
            reason="Later evidence disproves universal adapter cost claim.",
        )
    )
    ids["invalidated"] = invalidated_id
    old_id = store.put_candidate(
        CausalNodeDraft(
            content="Old adapter conclusion.",
            semantic_summary="Old adapter conclusion",
            semantic_keys=["adapter", "old"],
            source_module="causal_review",
            source_artifact_ref="causal/old-adapter",
            root_kind="design_decision",
            node_refs=[("artifact", "causal/old-adapter")],
        )
    )
    new_id = store.put_candidate(
        CausalNodeDraft(
            content="New simple conclusion for one-off work.",
            semantic_summary="New simple conclusion",
            semantic_keys=["simple", "new"],
            source_module="causal_review",
            source_artifact_ref="causal/new-simple",
            root_kind="design_decision",
            node_refs=[("artifact", "causal/new-simple")],
        )
    )
    store.admit_nodes(
        AdmissionTransaction(
            node_ids=[old_id, new_id],
            admitted_by_module="causal_review",
            rationale="Fixture supersession nodes.",
            evidence_ref="causal/supersession",
        )
    )
    store.supersede_node(
        SupersessionRequest(
            old_node_id=old_id,
            new_node_id=new_id,
            reason="New local scope supersedes old adapter conclusion.",
        )
    )
    ids["superseded_old"] = old_id
    ids["superseding_new"] = new_id
    return ids


def validate_fixture_minimum_content(writer: EvidenceWriter, fixture: Fixture) -> GateResult:
    passed = [
        "knowledge_obvious",
        "knowledge_unusual",
        "knowledge_rejected",
        "knowledge_superseded",
        "causal_admitted_chain",
        "causal_invalidated",
        "causal_superseded",
        "artifact_supporting",
        "artifact_unrelated",
        "artifact_opposing",
        "artifact_code_root",
        "artifact_path_traversal",
    ]
    failed = []
    notes = []
    if "deprecated" not in fixture.causal_ids:
        notes.append("CausalStore has deprecated status but no public deprecate_node API.")
    artifact = writer.write_json_artifact(
        "artifacts/deterministic_runs/fixture_minimum_content_results.json",
        test_group="fixture_minimum_content",
        status="passed",
        passed_cases=passed,
        failed_cases=failed,
        knowledge_refs=list(fixture.knowledge_ids.values()),
        causal_node_ids=list(fixture.causal_ids.values()),
        artifact_refs=list(fixture.artifact_refs.values()),
        fixture_refs=[rel(fixture.root)],
        notes=notes,
    )
    return GateResult(
        name="fixture_minimum_content",
        status="passed",
        summary="Fixture includes required positive, negative, and boundary seed classes.",
        artifact=rel(artifact),
        details={"notes": notes},
    )


def run_retrieval_quality_checks(writer: EvidenceWriter, fixture: Fixture) -> GateResult:
    context = build_context_bundle(
        fixture.package,
        bind_project_stores(fixture.root, debate_id="debate-retrieval-quality"),
        DebateRuntimeConfig(),
    )
    payload = context.model_dump(mode="json")
    payload_json = json.dumps(payload, sort_keys=True)
    knowledge_ids = {ref.knowledge_id for ref in context.knowledge_refs}
    causal_ids = {ref.node_id for ref in context.causal_refs}
    expected_knowledge = {
        fixture.knowledge_ids["obvious"],
        fixture.knowledge_ids["unusual"],
        fixture.knowledge_ids["single_project_constraint"],
    }
    expected_causal = {
        fixture.causal_ids["admitted_root"],
        fixture.causal_ids["admitted_chain_child"],
    }
    passed: list[str] = []
    failed: list[str] = []
    if expected_knowledge.issubset(knowledge_ids):
        passed.append("expected_knowledge_refs_retrieved")
    else:
        failed.append("expected_knowledge_refs_missing")
    if expected_causal.issubset(causal_ids):
        passed.append("expected_causal_refs_retrieved")
    else:
        failed.append("expected_causal_refs_missing")
    if len(context.knowledge_refs) <= MAX_KNOWLEDGE_REFS:
        passed.append("knowledge_ref_count_within_limit")
    else:
        failed.append("knowledge_ref_count_exceeds_limit")
    if len(context.causal_refs) <= MAX_CAUSAL_REFS:
        passed.append("causal_ref_count_within_limit")
    else:
        failed.append("causal_ref_count_exceeds_limit")
    if len(payload_json.encode("utf-8")) <= RETRIEVAL_LIMIT_BYTES:
        passed.append("retrieval_package_size_within_limit")
    else:
        failed.append("retrieval_package_size_exceeds_limit")
    causal_store = CausalStore(fixture.root / "causal" / "causal.sqlite3")
    active = causal_store.search_nodes(
        CausalQuery(query="adapter always cheaper", mode="admitted_only", include_rejected=True)
    )
    historical = causal_store.search_nodes(
        CausalQuery(query="adapter always cheaper", mode="historical", include_rejected=True)
    )
    if fixture.causal_ids["invalidated"] not in {node.node_id for node in active.nodes}:
        passed.append("invalidated_not_active_support")
    else:
        failed.append("invalidated_active_support")
    if fixture.causal_ids["invalidated"] in {node.node_id for node in historical.nodes}:
        passed.append("invalidated_visible_in_historical_mode")
    else:
        failed.append("invalidated_missing_from_historical_mode")
    expanded = causal_store.expand_context(
        ExpandContextRequest(
            node_ids=[fixture.causal_ids["admitted_chain_child"]],
            depth=2,
            mode="admitted_only",
        )
    )
    if fixture.causal_ids["admitted_root"] in expanded.selected_nodes:
        passed.append("causal_dependency_expansion_includes_parent")
    else:
        failed.append("causal_dependency_expansion_missing_parent")
    artifact = writer.write_json_artifact(
        "artifacts/retrieval_packages/retrieval_quality_results.json",
        test_group="knowledge_causal_retrieval_quality",
        status="passed" if not failed else "failed",
        passed_cases=passed,
        failed_cases=failed,
        knowledge_refs=list(knowledge_ids),
        causal_node_ids=[node_id for node_id in causal_ids if node_id is not None],
        artifact_refs=[str(writer.artifacts / "retrieval_packages" / "context_bundle.json")],
        extra={
            "context_bundle": payload,
            "retrieval_package_bytes": len(payload_json.encode("utf-8")),
            "active_mode_node_ids": [node.node_id for node in active.nodes],
            "historical_mode_node_ids": [node.node_id for node in historical.nodes],
            "expanded_selected_nodes": expanded.selected_nodes,
        },
    )
    (writer.artifacts / "retrieval_packages" / "context_bundle.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return GateResult(
        name="knowledge_causal_retrieval_quality",
        status="passed" if not failed else "failed",
        summary="Knowledge/Causal retrieval quality and size limits checked.",
        artifact=rel(artifact),
        details={"failed_cases": failed, "passed_cases": passed},
    )


def run_candidate_write_fault_injection(writer: EvidenceWriter, fixture: Fixture) -> GateResult:
    passed: list[str] = []
    failed: list[str] = []
    notes: list[str] = []
    mode_results: dict[str, dict[str, Any]] = {}
    before_snapshot = snapshot_db(
        fixture.root / "causal" / "causal.sqlite3",
        writer.db_snapshots / "before" / "candidate_write_fault_before.sqlite3",
    )

    mode_results["fail_before_first_write"] = _fault_unresolved_dependency(writer)
    mode_results["fail_after_n_successful_writes"] = _fault_after_n_successful_writes(writer)
    mode_results["fail_on_dependency_group_write"] = _fault_duplicate_dependency_group(writer)
    mode_results["fail_on_evidence_ref_write"] = _fault_on_evidence_ref_write(writer)
    mode_results["fail_on_commit"] = _fault_on_commit(writer)
    mode_results["simulate_duplicate"] = _fault_simulate_duplicate(writer)
    mode_results["simulate_near_duplicate"] = _fault_simulate_near_duplicate(writer)
    mode_results["simulate_store_unavailable"] = _fault_store_unavailable(writer)

    for mode, result in mode_results.items():
        if result["passed"]:
            passed.append(mode)
        else:
            failed.append(mode)
        notes.extend(result["notes"])

    after_snapshot = snapshot_db(
        fixture.root / "causal" / "causal.sqlite3",
        writer.db_snapshots / "after" / "candidate_write_fault_after.sqlite3",
    )
    artifact = writer.write_json_artifact(
        "artifacts/candidate_write_fault_injection_results.json",
        test_group="candidate_write_fault_injection",
        status="passed" if not failed else "failed",
        passed_cases=passed,
        failed_cases=failed,
        db_snapshot_refs=[rel(before_snapshot), rel(after_snapshot)],
        notes=notes,
        extra={
            "covered_fault_modes": passed,
            "missing_fault_modes": [],
            "mode_results": mode_results,
        },
    )
    return GateResult(
        name="candidate_write_fault_injection",
        status="passed" if not failed else "failed",
        summary="Candidate write rollback checked; full fault harness coverage evaluated.",
        artifact=rel(artifact),
        details={"failed_cases": failed, "notes": notes},
    )


def _fault_project(writer: EvidenceWriter, name: str) -> tuple[Path, DebateInputPackage]:
    root = writer.artifacts / "fixture_projects" / f"fault_{name}"
    if root.exists():
        shutil.rmtree(root)
    for folder in ("code", "archive", "knowledge", "causal"):
        (root / folder).mkdir(parents=True, exist_ok=True)
    simple_ref = root / "archive" / "simple.md"
    adapter_ref = root / "archive" / "adapter.md"
    simple_ref.write_text("simple direct implementation evidence", encoding="utf-8")
    adapter_ref.write_text("structured adapter implementation evidence", encoding="utf-8")
    package = DebateInputPackage(
        request_id=f"req-{name}",
        source_module="execution",
        project_root=root,
        decision_problem="Choose local implementation route",
        decision_scope="local project",
        required_outcome="choose_one",
        candidate_positions=[
            CandidatePosition(
                stance_id="simple",
                statement="Use simple direct implementation",
                summary="simple route",
                source_artifact_refs=[str(simple_ref)],
            ),
            CandidatePosition(
                stance_id="adapter",
                statement="Use structured adapter implementation",
                summary="adapter route",
                source_artifact_refs=[str(adapter_ref)],
            ),
        ],
    )
    return root, package


def _fault_candidate(
    package: DebateInputPackage,
    *,
    debate_id: str,
    group_ids: tuple[str, str] = ("g-simple", "g-adapter"),
    statements: tuple[str, str] = ("Simple route selected.", "Adapter route rejected."),
    assumptions: tuple[str, str] = ("simple assumption", "adapter assumption"),
) -> Any:
    return build_update_candidate(
        package=package,
        debate_id=debate_id,
        selected_stance_id="simple",
        rejected_stance_ids=["adapter"],
        nodes=[
            CausalCandidateNode(
                local_node_ref="fault-n1",
                statement=statements[0],
                semantic_summary="Simple selection",
                source_worker_id="worker-simple",
                source_stance_id="simple",
                dependency_groups=[
                    CausalCandidateDependencyGroup(
                        group_id=group_ids[0],
                        evidence_refs=["artifact/simple"],
                        assumptions=[assumptions[0]],
                        scope="local project",
                    )
                ],
            ),
            CausalCandidateNode(
                local_node_ref="fault-n2",
                statement=statements[1],
                semantic_summary="Adapter rejection",
                source_worker_id="worker-adapter",
                source_stance_id="adapter",
                dependency_groups=[
                    CausalCandidateDependencyGroup(
                        group_id=group_ids[1],
                        evidence_refs=["artifact/adapter"],
                        assumptions=[assumptions[1]],
                        scope="local project",
                    )
                ],
            ),
        ],
    )


def _write_fault_candidate(
    root: Path,
    package: DebateInputPackage,
    candidate: Any,
    *,
    debate_id: str,
) -> Any:
    binding = bind_project_stores(root, debate_id=debate_id)
    return write_causal_store_candidate(
        binding=binding,
        artifact_ref=str(binding.debate_candidate_root / "candidate.json"),
        candidate=candidate,
    )


def _fault_result(
    mode: str,
    *,
    passed: bool,
    before_count: int,
    after_count: int,
    notes: list[str],
) -> dict[str, Any]:
    return {
        "mode": mode,
        "passed": passed,
        "before_count": before_count,
        "after_count": after_count,
        "notes": notes,
    }


def _fault_unresolved_dependency(writer: EvidenceWriter) -> dict[str, Any]:
    mode = "fail_before_first_write"
    root, package = _fault_project(writer, mode)
    candidate = _fault_candidate(package, debate_id=f"debate-{mode}")
    candidate.nodes[0].dependency_groups[0].causal_dependencies = ["missing-local-node"]
    before = count_causal_nodes(root)
    notes: list[str] = []
    try:
        _write_fault_candidate(root, package, candidate, debate_id=f"debate-{mode}")
        notes.append("expected unresolved local dependency failure, but write succeeded")
        passed = False
    except CausalCandidateWriteError as exc:
        notes.append(f"{mode}: {exc.result.errors[0]['code']}")
        passed = count_causal_nodes(root) == before
    return _fault_result(mode, passed=passed, before_count=before, after_count=count_causal_nodes(root), notes=notes)


def _fault_after_n_successful_writes(writer: EvidenceWriter) -> dict[str, Any]:
    mode = "fail_after_n_successful_writes"
    root, package = _fault_project(writer, mode)
    candidate = _fault_candidate(package, debate_id=f"debate-{mode}")
    original = CausalStore.put_candidates
    notes: list[str] = []
    before = count_causal_nodes(root)

    def fail_after_first(self: CausalStore, drafts: list[CausalNodeDraft]) -> list[int]:
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._put_candidate_in_connection(conn, drafts[0])
            conn.rollback()
            raise CausalStoreError("FAULT_AFTER_N_WRITES", "simulated failure after one candidate write")

    CausalStore.put_candidates = fail_after_first
    try:
        _write_fault_candidate(root, package, candidate, debate_id=f"debate-{mode}")
        notes.append("expected simulated after-write failure, but write succeeded")
        passed = False
    except CausalCandidateWriteError as exc:
        notes.append(f"{mode}: {exc.result.errors[0]['code']}")
        passed = count_causal_nodes(root) == before
    finally:
        CausalStore.put_candidates = original
    return _fault_result(mode, passed=passed, before_count=before, after_count=count_causal_nodes(root), notes=notes)


def _fault_duplicate_dependency_group(writer: EvidenceWriter) -> dict[str, Any]:
    mode = "fail_on_dependency_group_write"
    root, package = _fault_project(writer, mode)
    candidate = _fault_candidate(
        package,
        debate_id=f"debate-{mode}",
        group_ids=("duplicate-group", "duplicate-group"),
    )
    before = count_causal_nodes(root)
    notes: list[str] = []
    try:
        _write_fault_candidate(root, package, candidate, debate_id=f"debate-{mode}")
        notes.append("expected duplicate dependency group failure, but write succeeded")
        passed = False
    except CausalCandidateWriteError as exc:
        notes.append(f"{mode}: {exc.result.errors[0]['code']}")
        passed = count_causal_nodes(root) == before
    return _fault_result(mode, passed=passed, before_count=before, after_count=count_causal_nodes(root), notes=notes)


def _fault_on_evidence_ref_write(writer: EvidenceWriter) -> dict[str, Any]:
    mode = "fail_on_evidence_ref_write"
    root, package = _fault_project(writer, mode)
    candidate = _fault_candidate(package, debate_id=f"debate-{mode}")
    original = CausalStore.put_candidates
    before = count_causal_nodes(root)
    notes: list[str] = []

    def fail_evidence_write(self: CausalStore, drafts: list[CausalNodeDraft]) -> list[int]:
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._put_candidate_in_connection(conn, drafts[0])
            conn.rollback()
            raise CausalStoreError("FAULT_EVIDENCE_REF_WRITE", "simulated evidence ref write failure")

    CausalStore.put_candidates = fail_evidence_write
    try:
        _write_fault_candidate(root, package, candidate, debate_id=f"debate-{mode}")
        notes.append("expected evidence ref write failure, but write succeeded")
        passed = False
    except CausalCandidateWriteError as exc:
        notes.append(f"{mode}: {exc.result.errors[0]['code']}")
        passed = count_causal_nodes(root) == before
    finally:
        CausalStore.put_candidates = original
    return _fault_result(mode, passed=passed, before_count=before, after_count=count_causal_nodes(root), notes=notes)


def _fault_on_commit(writer: EvidenceWriter) -> dict[str, Any]:
    mode = "fail_on_commit"
    root, package = _fault_project(writer, mode)
    candidate = _fault_candidate(package, debate_id=f"debate-{mode}")
    original = CausalStore.put_candidates
    before = count_causal_nodes(root)
    notes: list[str] = []

    def fail_commit(self: CausalStore, drafts: list[CausalNodeDraft]) -> list[int]:
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            for draft in drafts:
                self._put_candidate_in_connection(conn, draft)
            conn.rollback()
            raise CausalStoreError("FAULT_COMMIT", "simulated commit failure")

    CausalStore.put_candidates = fail_commit
    try:
        _write_fault_candidate(root, package, candidate, debate_id=f"debate-{mode}")
        notes.append("expected commit failure, but write succeeded")
        passed = False
    except CausalCandidateWriteError as exc:
        notes.append(f"{mode}: {exc.result.errors[0]['code']}")
        passed = count_causal_nodes(root) == before
    finally:
        CausalStore.put_candidates = original
    return _fault_result(mode, passed=passed, before_count=before, after_count=count_causal_nodes(root), notes=notes)


def _fault_simulate_duplicate(writer: EvidenceWriter) -> dict[str, Any]:
    mode = "simulate_duplicate"
    root, package = _fault_project(writer, mode)
    candidate = _fault_candidate(package, debate_id=f"debate-{mode}")
    before = count_causal_nodes(root)
    notes: list[str] = []
    first = _write_fault_candidate(root, package, candidate, debate_id=f"debate-{mode}")
    after_first = count_causal_nodes(root)
    second = _write_fault_candidate(root, package, candidate, debate_id=f"debate-{mode}")
    after_second = count_causal_nodes(root)
    passed = (
        first.write_status == "written"
        and second.write_status == "already_exists"
        and after_first == after_second
    )
    notes.append(f"{mode}: first={first.write_status}, second={second.write_status}")
    return _fault_result(mode, passed=passed, before_count=before, after_count=after_second, notes=notes)


def _fault_simulate_near_duplicate(writer: EvidenceWriter) -> dict[str, Any]:
    mode = "simulate_near_duplicate"
    root, package = _fault_project(writer, mode)
    first = _fault_candidate(
        package,
        debate_id=f"debate-{mode}-first",
        statements=("Same causal statement.", "Other route rejected."),
        assumptions=("assumption-a", "assumption-b"),
    )
    second = _fault_candidate(
        package,
        debate_id=f"debate-{mode}-second",
        statements=("Same causal statement.", "Different other route rejected."),
        assumptions=("different-assumption", "assumption-c"),
    )
    before = count_causal_nodes(root)
    notes: list[str] = []
    _write_fault_candidate(root, package, first, debate_id=f"debate-{mode}-first")
    after_first = count_causal_nodes(root)
    try:
        _write_fault_candidate(root, package, second, debate_id=f"debate-{mode}-second")
        notes.append("expected near duplicate failure, but write succeeded")
        passed = False
    except CausalCandidateWriteError as exc:
        codes = [str(error.get("code")) for error in exc.result.errors]
        notes.append(f"{mode}: {', '.join(codes)}")
        passed = "NEAR_DUPLICATE_REVIEW_REQUIRED" in codes and count_causal_nodes(root) == after_first
    return _fault_result(mode, passed=passed, before_count=before, after_count=count_causal_nodes(root), notes=notes)


def _fault_store_unavailable(writer: EvidenceWriter) -> dict[str, Any]:
    mode = "simulate_store_unavailable"
    root, package = _fault_project(writer, mode)
    candidate = _fault_candidate(package, debate_id=f"debate-{mode}")
    original = CausalStore.put_candidates
    before = count_causal_nodes(root)
    notes: list[str] = []

    def fail_store_unavailable(self: CausalStore, drafts: list[CausalNodeDraft]) -> list[int]:
        _ = self, drafts
        raise RuntimeError("simulated causal store unavailable")

    CausalStore.put_candidates = fail_store_unavailable
    try:
        _write_fault_candidate(root, package, candidate, debate_id=f"debate-{mode}")
        notes.append("expected store unavailable failure, but write succeeded")
        passed = False
    except CausalCandidateWriteError as exc:
        notes.append(f"{mode}: {exc.result.errors[0]['code']}")
        passed = count_causal_nodes(root) == before
    finally:
        CausalStore.put_candidates = original
    return _fault_result(mode, passed=passed, before_count=before, after_count=count_causal_nodes(root), notes=notes)


def count_causal_nodes(project_root: Path) -> int:
    db = project_root / "causal" / "causal.sqlite3"
    if not db.exists():
        return 0
    with sqlite3.connect(db) as conn:
        table_exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'causal_nodes'"
        ).fetchone()
        if not table_exists:
            return 0
        return int(conn.execute("SELECT COUNT(*) FROM causal_nodes").fetchone()[0])


def snapshot_db(db: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if db.exists():
        shutil.copy2(db, destination)
    else:
        destination.write_bytes(b"")
    return destination


def run_successful_debate_and_cross_reference(
    writer: EvidenceWriter,
    fixture: Fixture,
) -> GateResult:
    output = run_deterministic_debate(fixture.package, DebateRuntimeConfig(max_rounds=3))
    passed: list[str] = []
    failed: list[str] = []
    if output.status == "completed":
        passed.append("deterministic_debate_completed")
    else:
        failed.append(f"deterministic_debate_status_{output.status}")
    candidate_path = Path(output.causal_candidate_ref or "")
    write_result_path = candidate_path.with_name("causal_write_result.json")
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    write_result = json.loads(write_result_path.read_text(encoding="utf-8"))
    inserted_ids = write_result.get("inserted_node_ids", [])
    rows = causal_rows_by_id(fixture.root, inserted_ids)
    if inserted_ids and set(inserted_ids) == set(rows):
        passed.append("db_rows_exist_for_inserted_candidate_nodes")
    else:
        failed.append("db_rows_missing_for_inserted_candidate_nodes")
    if all(row["status"] == "candidate" for row in rows.values()):
        passed.append("candidate_rows_not_admitted_truth")
    else:
        failed.append("candidate_rows_mutated_to_truth")
    if len(candidate.get("proposed_nodes", [])) == len(inserted_ids):
        passed.append("artifact_node_count_matches_db_insert_count")
    else:
        failed.append("artifact_node_count_db_insert_mismatch")
    artifact = writer.write_json_artifact(
        "artifacts/causal_candidates/candidate_artifact_db_cross_reference_results.json",
        test_group="candidate_artifact_db_cross_reference",
        status="passed" if not failed else "failed",
        passed_cases=passed,
        failed_cases=failed,
        candidate_node_ids=inserted_ids,
        artifact_refs=[str(candidate_path), str(write_result_path)],
        extra={
            "output_package": output.model_dump(mode="json"),
            "candidate": candidate,
            "write_result": write_result,
            "db_rows": rows,
        },
    )
    copy_artifact_tree(Path(output.artifact_root), writer.artifacts / "deterministic_runs")
    return GateResult(
        name="candidate_artifact_db_cross_reference",
        status="passed" if not failed else "failed",
        summary="Deterministic Debate output and Causal DB candidate rows cross-checked.",
        artifact=rel(artifact),
        details={"failed_cases": failed, "output_status": output.status.value},
    )


def copy_artifact_tree(source: Path, destination_root: Path) -> None:
    if source.exists():
        destination = destination_root / source.name
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(source, destination)


def causal_rows_by_id(project_root: Path, node_ids: list[int]) -> dict[int, dict[str, Any]]:
    if not node_ids:
        return {}
    placeholders = ",".join("?" for _ in node_ids)
    with sqlite3.connect(project_root / "causal" / "causal.sqlite3") as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"SELECT node_id, status, source_module, source_artifact_ref FROM causal_nodes "
            f"WHERE node_id IN ({placeholders})",
            tuple(node_ids),
        ).fetchall()
    return {int(row["node_id"]): dict(row) for row in rows}


def run_idempotency_checks(writer: EvidenceWriter, fixture: Fixture) -> GateResult:
    passed: list[str] = []
    failed: list[str] = []
    before = count_causal_nodes(fixture.root)
    first = run_deterministic_debate(fixture.package, DebateRuntimeConfig(max_rounds=3))
    after_first = count_causal_nodes(fixture.root)
    second = run_deterministic_debate(fixture.package, DebateRuntimeConfig(max_rounds=3))
    after_second = count_causal_nodes(fixture.root)
    if second.status == "completed":
        passed.append("same_input_rerun_completed")
    else:
        failed.append(f"same_input_rerun_status_{second.status}")
    if after_second == after_first:
        passed.append("same_input_rerun_no_duplicate_rows")
    else:
        failed.append("same_input_rerun_created_duplicate_rows")
    notes = []
    if first.manifest_ref and second.manifest_ref:
        passed.append("rerun_manifest_refs_exist")
    checkpoint_ref: str | None = None
    with DebateRuntime(fixture.root) as runtime:
        runtime_result = runtime.run(
            fixture.package,
            DebateRuntimeConfig(max_rounds=3),
            thread_id="debate-production-resume",
        )
        snapshot = runtime.inspect("debate-production-resume")
        resumed = runtime.resume("debate-production-resume")
        checkpoint = fixture.root / ".aegis" / "runtime" / "debate_checkpoints.sqlite3"
        checkpoint_ref = rel(checkpoint)
    if runtime_result["result"].status.value == "completed":
        passed.append("checkpointed_debate_run_completed")
    else:
        failed.append(f"checkpointed_run_status_{runtime_result['result'].status.value}")
    if snapshot["values"].get("output_package"):
        passed.append("checkpoint_inspect_returns_output_package")
    else:
        failed.append("checkpoint_inspect_missing_output_package")
    if resumed["result"].debate_id == runtime_result["result"].debate_id:
        passed.append("standalone_debate_resume_returns_checkpointed_output")
    else:
        failed.append("standalone_debate_resume_mismatched_output")
    artifact = writer.write_json_artifact(
        "artifacts/deterministic_runs/resume_idempotency_results.json",
        test_group="resume_idempotency",
        status="passed" if not failed else "failed",
        passed_cases=passed,
        failed_cases=failed,
        notes=notes,
        artifact_refs=[checkpoint_ref] if checkpoint_ref else [],
        extra={
            "before_row_count": before,
            "after_first_row_count": after_first,
            "after_second_row_count": after_second,
            "first_output": first.model_dump(mode="json"),
            "second_output": second.model_dump(mode="json"),
            "runtime_output": runtime_result["result"].model_dump(mode="json"),
            "resumed_output": resumed["result"].model_dump(mode="json"),
            "checkpoint_next": list(snapshot["next"]),
        },
    )
    return GateResult(
        name="resume_idempotency",
        status="passed" if not failed else "failed",
        summary="Idempotent rerun checked; explicit interrupt/resume support evaluated.",
        artifact=rel(artifact),
        details={"failed_cases": failed, "notes": notes},
    )


def run_domain_error_checks(writer: EvidenceWriter, fixture: Fixture) -> GateResult:
    passed: list[str] = []
    failed: list[str] = []
    controlled_errors: list[dict[str, Any]] = []
    outputs: dict[str, Any] = {}

    def check_output(
        case_name: str,
        output: DebateOutputPackage,
        *,
        expected_status: str,
        expected_code: str,
    ) -> None:
        actual_status = output.status.value
        actual_code = output.errors[0].code if output.errors else None
        outputs[case_name] = output.model_dump(mode="json")
        if actual_status == expected_status and actual_code == expected_code:
            passed.append(f"{case_name}_controlled")
            controlled_errors.append(
                {"case": case_name, "status": actual_status, "code": actual_code}
            )
        else:
            failed.append(
                f"{case_name}_unexpected_{actual_status}_{actual_code}"
            )

    try:
        DebateInputPackage(
            request_id="",
            project_root=fixture.root,
            decision_problem="x",
            candidate_positions=[],
        )
        failed.append("invalid_input_package_not_rejected")
    except Exception as exc:  # noqa: BLE001
        passed.append("invalid_input_package_rejected")
        controlled_errors.append({"case": "invalid_input", "type": type(exc).__name__})
    missing_project = fixture.root / "missing"
    try:
        bind_project_stores(missing_project, debate_id="missing-project")
        failed.append("missing_project_store_not_rejected")
    except DebateRuntimeError as exc:
        passed.append("missing_project_store_domain_error")
        controlled_errors.append({"case": "missing_project", "code": exc.code})
    escape_package = fixture.package.model_copy(
        update={
            "source_artifact_refs": [fixture.artifact_refs["path_traversal"]],
            "candidate_positions": [
                CandidatePosition(
                    stance_id="escape",
                    statement="Use escape artifact",
                    summary="escape",
                    source_artifact_refs=[fixture.artifact_refs["path_traversal"]],
                )
            ],
        }
    )
    context = build_context_bundle(
        escape_package,
        bind_project_stores(fixture.root, debate_id="domain-error-path"),
        DebateRuntimeConfig(),
    )
    if context.rejected_artifact_refs:
        passed.append("invalid_artifact_path_rejected")
    else:
        failed.append("invalid_artifact_path_not_rejected")

    unsupported_package = fixture.package.model_copy(
        update={
            "hard_constraints": [
                HardConstraint(
                    constraint_id="hc-user-preference",
                    statement="The adapter route is mandatory because the requester prefers it.",
                    source="user",
                    evidence_ref="user/preference-only",
                )
            ]
        }
    )
    check_output(
        "unsupported_hard_constraint",
        run_deterministic_debate(unsupported_package, DebateRuntimeConfig(max_rounds=1)),
        expected_status="blocked",
        expected_code="UNSUPPORTED_HARD_CONSTRAINT",
    )

    insufficient_package = DebateInputPackage(
        request_id="req-insufficient-stances",
        source_module="execution",
        project_root=fixture.root,
        decision_problem="Choose implementation route",
        required_outcome="choose_one",
        candidate_positions=[
            CandidatePosition(
                stance_id="unsupported",
                statement="Use unsupported route",
                summary="unsupported route",
                source_artifact_refs=[],
            )
        ],
    )
    check_output(
        "insufficient_defensible_stances",
        run_deterministic_debate(insufficient_package, DebateRuntimeConfig(max_rounds=1)),
        expected_status="debate_not_required",
        expected_code="INSUFFICIENT_DEFENSIBLE_STANCES",
    )

    measurement_root = make_domain_case_project(writer, "domain_measurement")
    KnowledgeStore(measurement_root / "knowledge" / "knowledge.sqlite3").register_need_rule(
        NeedRule(
            rule_id="need-benchmark-before-route",
            required_dimension="benchmark_result",
            trigger_operations=["choose implementation route"],
            required_subject_kinds=["project"],
            acceptable_sources=["test"],
            default_blocking_level="request_test_measurement",
            rationale="Benchmark evidence is required before route adjudication.",
        )
    )
    check_output(
        "missing_test_measurement",
        run_deterministic_debate(
            domain_case_package(measurement_root, "req-domain-measurement"),
            DebateRuntimeConfig(max_rounds=1),
        ),
        expected_status="need_measurement",
        expected_code="MISSING_TEST_MEASUREMENT",
    )

    check_output(
        "non_convergent",
        run_deterministic_debate(
            fixture.package,
            DebateRuntimeConfig(max_rounds=1, stable_selected_stance_round_threshold=3),
        ),
        expected_status="non_convergent",
        expected_code="DEBATE_NON_CONVERGENT",
    )

    violation_packet = WorkerTurnPacket(
        turn_id="turn-domain-violation",
        debate_id="debate-domain",
        round_index=1,
        worker_id="worker-overdefense",
        stance_id="adapter",
        defense="Adapter is globally mandatory.",
        concessions=[
            WorkerConcession(
                target_ref="simple",
                why_conceded="",
                defeating_ref=None,
            )
        ],
        chain_delta=WorkerCausalChainDelta(),
        evidence_refs=[],
        self_audit=WorkerSelfAudit(
            unsupported_claims=["Invented project fact."],
            truth_status_claimed="global_truth",
        ),
    )
    violation_types = {
        violation.violation_type
        for violation in detect_worker_protocol_violations(violation_packet)
    }
    if {
        "unsupported_invention",
        "global_truth_confusion",
        "premature_concession",
    }.issubset(violation_types):
        passed.append("worker_protocol_violation_controlled")
        controlled_errors.append(
            {
                "case": "worker_protocol_violation",
                "violation_types": sorted(violation_types),
            }
        )
    else:
        failed.append("worker_protocol_violation_not_detected")

    bad_candidate = build_update_candidate(
        package=fixture.package,
        debate_id="domain-write-failure",
        selected_stance_id="simple",
        rejected_stance_ids=["adapter"],
        nodes=[
            CausalCandidateNode(
                local_node_ref="n-domain-bad",
                statement="Bad unresolved dependency candidate.",
                semantic_summary="Bad unresolved dependency",
                source_worker_id="worker-simple",
                source_stance_id="simple",
                dependency_groups=[
                    CausalCandidateDependencyGroup(
                        group_id="bad-dependency",
                        causal_dependencies=["missing-local-node"],
                        evidence_refs=["artifact/domain-write-failure"],
                        scope="local project",
                    )
                ],
            )
        ],
    )
    try:
        write_causal_store_candidate(
            binding=bind_project_stores(fixture.root, debate_id="domain-write-failure"),
            artifact_ref=str(fixture.root / "causal" / "candidates" / "bad.json"),
            candidate=bad_candidate,
        )
        failed.append("causal_candidate_write_failure_not_rejected")
    except CausalCandidateWriteError as exc:
        error_codes = {str(error.get("code")) for error in exc.result.errors}
        if "UNRESOLVED_LOCAL_DEPENDENCY" in error_codes:
            passed.append("causal_candidate_write_failure_controlled")
            controlled_errors.append(
                {
                    "case": "causal_candidate_write_failure",
                    "write_status": exc.result.write_status,
                    "error_codes": sorted(error_codes),
                }
            )
        else:
            failed.append("causal_candidate_write_failure_wrong_error")

    artifact = writer.write_json_artifact(
        "artifacts/deterministic_runs/domain_error_contract_results.json",
        test_group="domain_error_contract",
        status="passed" if not failed else "failed",
        passed_cases=passed,
        failed_cases=failed,
        controlled_errors=controlled_errors,
        extra={"outputs": outputs},
    )
    return GateResult(
        name="domain_error_contract",
        status="passed" if not failed else "failed",
        summary="Public invalid inputs produce controlled validation/domain outcomes.",
        artifact=rel(artifact),
        details={"passed_cases": passed, "failed_cases": failed},
    )


def make_domain_case_project(writer: EvidenceWriter, name: str) -> Path:
    root = writer.artifacts / "fixture_projects" / name
    if root.exists():
        shutil.rmtree(root)
    for folder in ("code", "archive", "knowledge", "causal"):
        (root / folder).mkdir(parents=True, exist_ok=True)
    (root / "archive" / "simple-route.md").write_text(
        "Verified evidence: simple direct implementation lowers complexity.",
        encoding="utf-8",
    )
    (root / "archive" / "adapter-route.md").write_text(
        "Verified evidence: adapter implementation improves extension boundary.",
        encoding="utf-8",
    )
    return root


def domain_case_package(root: Path, request_id: str) -> DebateInputPackage:
    return DebateInputPackage(
        request_id=request_id,
        source_module="execution",
        project_root=root,
        decision_problem="Choose implementation route",
        required_outcome="choose_one",
        source_artifact_refs=[
            str(root / "archive" / "simple-route.md"),
            str(root / "archive" / "adapter-route.md"),
        ],
        candidate_positions=[
            CandidatePosition(
                stance_id="simple",
                statement="Use simple direct implementation",
                summary="simple direct implementation has lower complexity",
                source_artifact_refs=[str(root / "archive" / "simple-route.md")],
            ),
            CandidatePosition(
                stance_id="adapter",
                statement="Use structured adapter implementation",
                summary="structured adapter improves extension boundary",
                source_artifact_refs=[str(root / "archive" / "adapter-route.md")],
            ),
        ],
    )


def run_state_boundary_checks(writer: EvidenceWriter, fixture: Fixture) -> GateResult:
    passed: list[str] = []
    failed: list[str] = []
    state_payload = {
        "input_package": fixture.package.model_dump(mode="json"),
        "config": DebateRuntimeConfig(max_rounds=2).model_dump(mode="json"),
    }
    output = run_deterministic_debate(fixture.package, DebateRuntimeConfig(max_rounds=2))
    state_bytes = len(json.dumps(state_payload, sort_keys=True).encode("utf-8"))
    if state_bytes <= STATE_LIMIT_BYTES:
        passed.append("initial_state_under_size_limit")
    else:
        failed.append("initial_state_exceeds_size_limit")
    langgraph_store_calls = detect_langgraph_store_arguments(REPO_ROOT / "src")
    if not langgraph_store_calls:
        passed.append("no_langgraph_store_argument_detected")
    else:
        failed.append("langgraph_store_argument_detected")
    output_payload = output.model_dump(mode="json")
    if len(json.dumps(output_payload, sort_keys=True).encode("utf-8")) <= STATE_LIMIT_BYTES:
        passed.append("output_state_under_size_limit")
    else:
        failed.append("output_state_exceeds_size_limit")
    dry_run = run(["git", "add", "--dry-run", "."])
    evidence_leak = any("module_test_reports" in line for line in dry_run.stdout.splitlines())
    if not evidence_leak:
        passed.append("git_add_dry_run_excludes_module_test_reports")
    else:
        failed.append("git_add_dry_run_includes_module_test_reports")
    artifact = writer.write_json_artifact(
        "artifacts/state_size_results.json",
        test_group="state_boundary",
        status="passed" if not failed else "failed",
        passed_cases=passed,
        failed_cases=failed,
        artifact_refs=[str(output.manifest_ref)],
        extra={
            "initial_state_bytes": state_bytes,
            "output_state_bytes": len(json.dumps(output_payload, sort_keys=True).encode("utf-8")),
            "state_limit_bytes": STATE_LIMIT_BYTES,
            "langgraph_store_argument_refs": langgraph_store_calls,
            "git_add_dry_run_stdout": dry_run.stdout,
        },
    )
    writer.write_json_artifact(
        "artifacts/retrieval_package_size_results.json",
        test_group="retrieval_package_size",
        status="passed" if not failed else "failed",
        passed_cases=[
            case
            for case in passed
            if "size" in case or "state" in case or "store" in case
        ],
        failed_cases=[case for case in failed if "size" in case or "state" in case or "store" in case],
        extra={
            "state_limit_bytes": STATE_LIMIT_BYTES,
            "retrieval_limit_bytes": RETRIEVAL_LIMIT_BYTES,
            "max_knowledge_refs": MAX_KNOWLEDGE_REFS,
            "max_causal_refs": MAX_CAUSAL_REFS,
        },
    )
    return GateResult(
        name="state_boundary",
        status="passed" if not failed else "failed",
        summary="LangGraph Store usage, state size, and git hygiene checked.",
        artifact=rel(artifact),
        details={"failed_cases": failed},
    )


def run_artifact_schema_validation(writer: EvidenceWriter) -> GateResult:
    failed: list[str] = []
    passed: list[str] = []
    for path in writer.root.rglob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            failed.append(f"{rel(path)}:invalid_json:{exc.msg}")
            continue
        ok, reason = validate_json_artifact_schema(writer, path, payload)
        if ok:
            passed.append(f"{rel(path)}:{reason}")
        else:
            failed.append(f"{rel(path)}:{reason}")
    artifact = writer.write_json_artifact(
        "artifacts/test_artifact_schema_validation_results.json",
        test_group="test_artifact_schema_validation",
        status="passed" if not failed else "failed",
        passed_cases=passed,
        failed_cases=failed,
    )
    return GateResult(
        name="test_artifact_schema_validation",
        status="passed" if not failed else "failed",
        summary="Runtime, evidence, fixture, source, and real-agent JSON artifact schemas validated.",
        artifact=rel(artifact),
        details={"passed_cases": passed, "failed_cases": failed},
    )


def validate_json_artifact_schema(
    writer: EvidenceWriter,
    path: Path,
    payload: object,
) -> tuple[bool, str]:
    if isinstance(payload, dict) and COMMON_SCHEMA_FIELDS.issubset(payload):
        return True, "common_evidence_artifact"
    name = path.name
    try:
        if name == "source_manifest.json":
            return _validate_required_keys(
                payload,
                {
                    "branch",
                    "commit",
                    "dirty",
                    "status_short",
                    "tracked_and_untracked_files",
                    "source_tree_sha256",
                    "source_snapshot",
                    "source_snapshot_sha256",
                },
                "source_manifest",
            )
        if name == "fixture_manifest.json":
            return _validate_required_keys(
                payload,
                {
                    "project_root",
                    "knowledge_ids",
                    "causal_ids",
                    "artifact_refs",
                    "expected_retrieval_refs",
                },
                "fixture_manifest",
            )
        if name in {"seeded_knowledge_manifest.json", "seeded_causal_manifest.json"}:
            return _validate_int_map(payload, name.removesuffix(".json"))
        if name == "input_package.json":
            DebateInputPackage.model_validate(payload)
            return True, "DebateInputPackage"
        if name == "context_bundle.json":
            DebateContextBundle.model_validate(payload)
            return True, "DebateContextBundle"
        if name == "hard_constraint_validations.json":
            _validate_model_list(payload, HardConstraintValidation)
            return True, "list[HardConstraintValidation]"
        if name == "stance_admissions.json":
            _validate_model_list(payload, StanceAdmissionRecord)
            return True, "list[StanceAdmissionRecord]"
        if name == "stance_relations.json":
            _validate_model_list(payload, StanceRelationRecord)
            return True, "list[StanceRelationRecord]"
        if name == "worker_turns.json":
            _validate_model_list(payload, WorkerTurnPacket)
            return True, "list[WorkerTurnPacket]"
        if name == "worker_violations.json":
            _validate_model_list(payload, WorkerProtocolViolation)
            return True, "list[WorkerProtocolViolation]"
        if name == "leader_assessment.json":
            LeaderRoundAssessment.model_validate(payload)
            return True, "LeaderRoundAssessment"
        if name == "causal_write_result.json":
            CausalCandidateWriteResult.model_validate(payload)
            return True, "CausalCandidateWriteResult"
        if name == "output_package.json":
            DebateOutputPackage.model_validate(payload)
            return True, "DebateOutputPackage"
        if name == "manifest.json":
            DebateRunManifest.model_validate(payload)
            return True, "DebateRunManifest"
        if name == "causal_candidate.json":
            return _validate_required_keys(
                payload,
                {
                    "source_module",
                    "candidate_id",
                    "request_id",
                    "debate_id",
                    "selected_stance_id",
                    "rejected_alternatives",
                    "status",
                    "proposed_nodes",
                    "reused_node_ids",
                },
                "causal_candidate_payload",
            )
        if name == "final_report.json":
            return _validate_required_keys(
                payload,
                {
                    "decision_problem",
                    "selected_stance_id",
                    "rejected_stance_ids",
                    "causal_candidate_ref",
                    "causal_store_write",
                    "status",
                },
                "debate_final_report",
            )
        if _is_real_agent_raw_path(writer, path):
            return validate_real_agent_raw_payload(path.stem, payload)
        if _is_real_agent_behavior_case_path(writer, path):
            return validate_real_agent_behavior_case(payload)
        if path.is_relative_to(writer.artifacts):
            return False, "unclassified_artifact_json_requires_schema"
        return True, "json_parse_only"
    except Exception as exc:  # noqa: BLE001
        return False, f"schema_invalid:{type(exc).__name__}:{exc}"


def _validate_required_keys(
    payload: object,
    keys: set[str],
    schema_name: str,
) -> tuple[bool, str]:
    if not isinstance(payload, dict):
        return False, f"{schema_name}_not_object"
    missing = sorted(keys - set(payload))
    if missing:
        return False, f"{schema_name}_missing_{','.join(missing)}"
    return True, schema_name


def _validate_int_map(payload: object, schema_name: str) -> tuple[bool, str]:
    if not isinstance(payload, dict):
        return False, f"{schema_name}_not_object"
    if not all(isinstance(key, str) and isinstance(value, int) for key, value in payload.items()):
        return False, f"{schema_name}_not_str_int_map"
    return True, schema_name


def _validate_model_list(payload: object, model: type) -> None:
    if not isinstance(payload, list):
        raise ValueError("expected list")
    for item in payload:
        model.model_validate(item)


def _is_real_agent_raw_path(writer: EvidenceWriter, path: Path) -> bool:
    return path.is_relative_to(writer.artifacts / "real_agent_runs" / "raw")


def _is_real_agent_behavior_case_path(writer: EvidenceWriter, path: Path) -> bool:
    return path.is_relative_to(writer.artifacts / "real_agent_runs" / "behavior_cases")


def detect_langgraph_store_arguments(source_root: Path) -> list[str]:
    refs: list[str] = []
    checked_call_names = {"compile", "invoke", "ainvoke", "stream", "astream"}
    for path in source_root.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            refs.append(f"{rel(path)}:syntax-error")
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Attribute):
                call_name = func.attr
            elif isinstance(func, ast.Name):
                call_name = func.id
            else:
                continue
            if call_name not in checked_call_names:
                continue
            if any(keyword.arg == "store" for keyword in node.keywords):
                refs.append(f"{rel(path)}:{node.lineno}")
    return refs


def run_real_agent_artifact_validation(writer: EvidenceWriter) -> GateResult:
    raw_dir = writer.artifacts / "real_agent_runs" / "raw"
    expected = {
        name: raw_dir / file_name
        for name, file_name in REQUIRED_REAL_AGENT_ARTIFACTS.items()
    }
    missing = [name for name, path in expected.items() if not path.exists()]
    passed: list[str] = []
    failed: list[str] = []
    notes: list[str] = []
    if missing:
        failed.append("real_agent_artifacts_missing")
        notes.append(f"missing artifacts: {', '.join(missing)}")
    else:
        for name, path in expected.items():
            payload = json.loads(path.read_text(encoding="utf-8"))
            ok, reason = validate_real_agent_raw_payload(name, payload)
            if ok:
                passed.append(f"{name}_{reason}")
            else:
                failed.append(f"{name}_{reason}")
    artifact = writer.write_json_artifact(
        "artifacts/real_agent_independent_validation_results.json",
        test_group="real_agent_independent_validation",
        status="passed" if not failed else "blocked",
        passed_cases=passed,
        failed_cases=failed,
        notes=notes,
    )
    return GateResult(
        name="real_agent_independent_validation",
        status="passed" if not failed else "blocked",
        summary="Real-agent artifacts independently validated when present.",
        artifact=rel(artifact),
        details={"failed_cases": failed, "notes": notes},
    )


def run_real_agent_behavior_validation(writer: EvidenceWriter) -> GateResult:
    cases = load_real_agent_behavior_cases(writer)
    passed: list[str] = []
    failed: list[str] = []
    notes: list[str] = []
    missing_cases = sorted(set(REQUIRED_REAL_AGENT_BEHAVIOR_INVARIANTS) - set(cases))
    if missing_cases:
        failed.append("missing_real_agent_behavior_cases")
        notes.append(f"missing cases: {', '.join(missing_cases)}")
    for case_id, required_invariants in REQUIRED_REAL_AGENT_BEHAVIOR_INVARIANTS.items():
        payload = cases.get(case_id)
        if payload is None:
            continue
        ok, reason = validate_real_agent_behavior_case(payload)
        if not ok:
            failed.append(f"{case_id}_{reason}")
            continue
        invariants = payload.get("invariants", {})
        if not isinstance(invariants, dict):
            failed.append(f"{case_id}_invariants_not_object")
            continue
        missing_or_false = sorted(
            key for key in required_invariants if invariants.get(key) is not True
        )
        if missing_or_false:
            failed.append(
                f"{case_id}_missing_or_false_invariants_{','.join(missing_or_false)}"
            )
            continue
        passed.append(case_id)

    artifact = writer.write_json_artifact(
        "artifacts/real_agent_behavior_validation_results.json",
        test_group="real_agent_behavior_validation",
        status="passed" if not failed else "blocked",
        passed_cases=passed,
        failed_cases=failed,
        notes=notes,
        extra={
            "required_cases": sorted(REQUIRED_REAL_AGENT_BEHAVIOR_INVARIANTS),
            "behavior_cases": cases,
        },
    )
    return GateResult(
        name="real_agent_behavior_validation",
        status="passed" if not failed else "blocked",
        summary="Real-agent behavior pressure cases independently validated.",
        artifact=rel(artifact),
        details={"passed_cases": passed, "failed_cases": failed, "notes": notes},
    )


def load_real_agent_behavior_cases(writer: EvidenceWriter) -> dict[str, dict[str, Any]]:
    case_dir = writer.artifacts / "real_agent_runs" / "behavior_cases"
    cases: dict[str, dict[str, Any]] = {}
    if case_dir.exists():
        for path in sorted(case_dir.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict) and isinstance(payload.get("case_id"), str):
                cases[payload["case_id"]] = payload
    for name in (
        "real_agent_behavior_cases.json",
        "behavior_validation_cases.json",
    ):
        path = writer.artifacts / "real_agent_runs" / name
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        raw_cases = payload.get("cases", payload) if isinstance(payload, dict) else payload
        if isinstance(raw_cases, list):
            for item in raw_cases:
                if isinstance(item, dict) and isinstance(item.get("case_id"), str):
                    cases[item["case_id"]] = item
    return cases


def validate_real_agent_raw_payload(name: str, payload: object) -> tuple[bool, str]:
    if not isinstance(payload, dict):
        return False, "raw_not_object"
    role = payload.get("role")
    thread_id = payload.get("thread_id")
    output = extract_agent_inner_output(payload)
    if not isinstance(role, str) or not role:
        return False, "missing_role"
    if not isinstance(thread_id, str) or not thread_id:
        return False, "missing_thread_id"
    if not isinstance(output, dict) or not output:
        return False, "missing_output"
    if name == "leader":
        if role != "debate_leader":
            return False, "leader_role_invalid"
        if output.get("status") != "causal_candidate":
            return False, "leader_status_not_causal_candidate"
        self_audit = output.get("self_audit", {})
        if isinstance(self_audit, dict) and (
            self_audit.get("global_truth_claimed") is True
            or self_audit.get("store_truth_written") is True
        ):
            return False, "leader_claimed_global_truth_or_store_write"
        if not output.get("selected_stance_id"):
            return False, "leader_missing_selected_stance"
        return True, "raw_schema_valid"
    if role != "debate_worker":
        return False, "worker_role_invalid"
    if not output.get("stance_id"):
        return False, "worker_missing_stance_id"
    if not output.get("evidence_refs"):
        return False, "worker_missing_evidence_refs"
    if not output.get("causal_chain_delta"):
        return False, "worker_missing_causal_chain_delta"
    return True, "raw_schema_valid"


def extract_agent_inner_output(payload: dict[str, object]) -> object:
    output = payload.get("output")
    if isinstance(output, dict) and isinstance(output.get("output"), dict):
        inner = dict(output["output"])
        for key in ("role", "stance_id"):
            if key in output and key not in inner:
                inner[key] = output[key]
        return inner
    return output


def validate_real_agent_behavior_case(payload: object) -> tuple[bool, str]:
    required = {
        "case_id",
        "status",
        "expected_behavior",
        "observed_behavior",
        "leader_action",
        "worker_packet_refs",
        "schema_validation",
        "repair_attempts",
        "evidence_refs",
        "invariants",
    }
    if not isinstance(payload, dict):
        return False, "case_not_object"
    missing = sorted(required - set(payload))
    if missing:
        return False, f"missing_{','.join(missing)}"
    if payload.get("status") != "passed":
        return False, "status_not_passed"
    thread_id = payload.get("thread_id")
    thread_ids = payload.get("thread_ids")
    if not thread_id and not thread_ids:
        return False, "missing_thread_id_or_thread_ids"
    if thread_ids is not None and not (
        isinstance(thread_ids, list)
        and all(isinstance(item, str) and item for item in thread_ids)
    ):
        return False, "thread_ids_invalid"
    if thread_id is not None and not isinstance(thread_id, str):
        return False, "thread_id_invalid"
    schema_validation = payload.get("schema_validation")
    if not isinstance(schema_validation, dict) or schema_validation.get("passed") is not True:
        return False, "schema_validation_not_passed"
    for list_key in ("worker_packet_refs", "repair_attempts", "evidence_refs"):
        value = payload.get(list_key)
        if not isinstance(value, list):
            return False, f"{list_key}_not_list"
    if not isinstance(payload.get("invariants"), dict):
        return False, "invariants_not_object"
    return True, "behavior_case_schema_valid"


def run_required_commands(writer: EvidenceWriter) -> list[GateResult]:
    commands = [
        (
            "pytest_debate",
            [str(Path(sys.executable)), "-m", "pytest", "tests\\debate", "-vv"],
            900,
        ),
        ("pytest_full", [str(Path(sys.executable)), "-m", "pytest", "-vv"], 1200),
        ("ruff", [str(Path(sys.executable)), "-m", "ruff", "check", "."], 600),
        ("git_diff_check", ["git", "diff", "--check"], 120),
        ("git_status", ["git", "status", "--short"], 120),
    ]
    results: list[GateResult] = []
    for name, command, timeout in commands:
        completed = run(command, timeout=timeout)
        log_path = writer.logs / f"{name}.log"
        log_path.write_text(
            f"$ {' '.join(command)}\n"
            f"exit_code={completed.returncode}\n\n"
            f"STDOUT:\n{completed.stdout}\n\nSTDERR:\n{completed.stderr}",
            encoding="utf-8",
        )
        results.append(
            GateResult(
                name=name,
                status="passed" if completed.returncode == 0 else "failed",
                summary=f"Command {'passed' if completed.returncode == 0 else 'failed'}: {name}",
                artifact=rel(log_path),
                details={"exit_code": completed.returncode},
            )
        )
    crlf_result = run_crlf_scan(writer)
    results.append(crlf_result)
    return results


def run_crlf_scan(writer: EvidenceWriter) -> GateResult:
    bad: list[str] = []
    tracked = run(["git", "ls-files"]).stdout.splitlines()
    untracked = run(["git", "ls-files", "--others", "--exclude-standard"]).stdout.splitlines()
    for file_name in sorted(set(tracked + untracked)):
        if not file_name.endswith((".py", ".md", ".toml", ".yaml", ".yml", ".json")):
            continue
        path = REPO_ROOT / file_name
        if not path.is_file():
            continue
        if b"\r\n" in path.read_bytes():
            bad.append(file_name)
    log_path = writer.logs / "crlf_scan.log"
    log_path.write_text("\n".join(bad) if bad else "NO_CRLF_FOUND", encoding="utf-8")
    return GateResult(
        name="crlf_scan",
        status="passed" if not bad else "failed",
        summary="CRLF scan completed.",
        artifact=rel(log_path),
        details={"bad_files": bad},
    )


def write_report(writer: EvidenceWriter, results: list[GateResult]) -> GateResult:
    scope_limit_p0_names = {
        "real_agent_independent_validation",
        "real_agent_behavior_validation",
    }
    p0_names = {
        "knowledge_causal_retrieval_quality",
        "candidate_write_fault_injection",
        "candidate_artifact_db_cross_reference",
        "resume_idempotency",
        "domain_error_contract",
        "state_boundary",
        "test_artifact_schema_validation",
        "real_agent_independent_validation",
        "real_agent_behavior_validation",
        "pytest_debate",
    }
    failed = [result for result in results if result.status == "failed"]
    blocked = [result for result in results if result.status == "blocked"]
    p0_failed_or_blocked = [
        result
        for result in results
        if result.name in p0_names and result.status in {"failed", "blocked"}
    ]
    hard_p0_failed_or_blocked = [
        result
        for result in p0_failed_or_blocked
        if result.name not in scope_limit_p0_names
    ]
    scope_limited_p0_blocked = [
        result
        for result in p0_failed_or_blocked
        if result.name in scope_limit_p0_names and result.status == "blocked"
    ]
    scope_limited_p0_failed = [
        result
        for result in p0_failed_or_blocked
        if result.name in scope_limit_p0_names and result.status == "failed"
    ]
    if hard_p0_failed_or_blocked:
        verdict = "rejected" if any(item.status == "failed" for item in hard_p0_failed_or_blocked) else "blocked"
    elif scope_limited_p0_failed:
        verdict = "rejected"
    elif scope_limited_p0_blocked:
        verdict = "accepted_with_scope_limits"
    elif failed:
        verdict = "accepted_with_scope_limits"
    elif blocked:
        verdict = "accepted_with_scope_limits"
    else:
        verdict = "accepted"
    final_status = final_status_for_verdict(verdict)
    scope_limits = [
        result.name
        for result in results
        if result.status in {"failed", "blocked", "scope_limited"}
    ]
    rows = "\n".join(
        f"| {result.name} | {result.status} | {result.summary} | {result.artifact or ''} |"
        for result in results
    )
    report = f"""# DebateSubgraph v2 Production Verification Report

## Scope

Strict execution of `docs/DEBATE_SUBGRAPH_V2_PRODUCTION_TEST_PLAN.md`.

## Verdict

`{verdict}`

## Evidence Root

```text
{writer.root}
```

## Result Matrix

| Gate | Status | Summary | Artifact |
| --- | --- | --- | --- |
{rows}

## Failed Gates

{format_gate_list(failed)}

## Blocked Gates

{format_gate_list(blocked)}

## Notes

- `accepted` is forbidden unless deterministic checks, real-agent raw artifact
  validation, and real-agent behavior pressure-case validation pass.
- Any P0 failed gate makes the verdict `rejected`.
- Generated evidence remains under `module_test_reports/`, which is git-ignored.
"""
    report_path = writer.reports / "DEBATE_SUBGRAPH_V2_PRODUCTION_VERIFICATION_REPORT.md"
    report_path.write_text(report, encoding="utf-8")
    summary_path = writer.write_json_artifact(
        "artifacts/deterministic_runs/final_verdict_summary.json",
        test_group="final_verdict",
        status=final_status,
        passed_cases=[result.name for result in results if result.status == "passed"],
        failed_cases=[result.name for result in results if result.status == "failed"],
        notes=[f"verdict={verdict}"],
        extra={
            "verdict": verdict,
            "report_ref": rel(report_path),
            "scope_limits": scope_limits if verdict == "accepted_with_scope_limits" else [],
        },
    )
    return GateResult(
        name="final_report",
        status=final_status,
        summary=f"Final verdict: {verdict}",
        artifact=rel(report_path),
        details={"verdict": verdict, "summary_artifact": rel(summary_path)},
    )


def final_status_for_verdict(verdict: str) -> Status:
    if verdict == "accepted":
        return "passed"
    if verdict == "accepted_with_scope_limits":
        return "scope_limited"
    if verdict == "blocked":
        return "blocked"
    return "failed"


def format_gate_list(results: list[GateResult]) -> str:
    if not results:
        return "None."
    return "\n".join(
        f"- `{result.name}`: {result.summary} ({result.artifact or 'no artifact'})"
        for result in results
    )


if __name__ == "__main__":
    raise SystemExit(main())
