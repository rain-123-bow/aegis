from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

State = dict[str, Any]

GRAPH_GATE_RESULT = "GRAPH_GATE_RESULT.json"
GRAPH_STATE_SNAPSHOT = "GRAPH_STATE_SNAPSHOT.json"
AUTHOR_PATCH_CLAIM = "AUTHOR_PATCH_CLAIM.json"
TEST_PLAN_REVIEW_RESULT = "TEST_PLAN_REVIEW_RESULT.json"
TEST_PLAN_REVIEW_BLOCKERS = "TEST_PLAN_REVIEW_BLOCKERS.json"
TEST_PLAN_BLOCKER_CLOSURE = "TEST_PLAN_BLOCKER_CLOSURE.json"
TEST_RESULT_REVIEW_RESULT = "TEST_RESULT_REVIEW_RESULT.json"
TEST_RESULT_REVIEW_BLOCKERS = "TEST_RESULT_REVIEW_BLOCKERS.json"
TEST_RESULT_BLOCKER_CLOSURE = "TEST_RESULT_BLOCKER_CLOSURE.json"
TEST_EXECUTION_CLAIM = "TEST_EXECUTION_CLAIM.json"

DEFAULT_TEST_PLAN_REQUIRED_FILES = [
    "TEST_PLAN.md",
    "TRACEABILITY_MATRIX.md",
    "TEST_CASE_INDEX.md",
]

DEFAULT_SCORE_THRESHOLD = int(os.environ.get("AEGIS_REVIEW_PASS_SCORE", "90"))
DEFAULT_MAX_REVIEW_FAILURES = int(os.environ.get("AEGIS_MAX_REVIEW_FAILURES", "5"))

NODE_A = "A"
NODE_B = "B"
NODE_C = "C"
NODE_D = "D"
NODE_E = "E"
NODE_F = "F"
ROUTE_END = "END"

CONTROL_FILES = {
    "author_patch_claim": AUTHOR_PATCH_CLAIM,
    "test_plan_review_result": TEST_PLAN_REVIEW_RESULT,
    "test_plan_review_blockers": TEST_PLAN_REVIEW_BLOCKERS,
    "test_plan_blocker_closure": TEST_PLAN_BLOCKER_CLOSURE,
    "test_execution_claim": TEST_EXECUTION_CLAIM,
    "test_result_review_result": TEST_RESULT_REVIEW_RESULT,
    "test_result_review_blockers": TEST_RESULT_REVIEW_BLOCKERS,
    "test_result_blocker_closure": TEST_RESULT_BLOCKER_CLOSURE,
    "graph_gate_result": GRAPH_GATE_RESULT,
    "graph_state_snapshot": GRAPH_STATE_SNAPSHOT,
}


AGENT_WRITABLE_OUTPUT_FIELDS = {
    "artifact_path",
    "status",
    "project_root",
    "requirement_design_doc",
    "implementation_plan_doc",
    "test_plan_doc",
    "approved_test_plan_doc",
    "executed_test_plan_doc",
    "coverage_matrix_doc",
    "execution_report_doc",
    "test_result_review_doc",
    "test_report_doc",
    "evidence_dir",
}

PROTECTED_AGENT_OUTPUT_FIELDS = {
    "current_node",
    "raw_status",
    "gate_status",
    "gate_route",
    "review_pass_score",
    "review_score",
    "effective_score",
    "open_blockers",
    "blocker_history",
    "same_blocker_counts",
    "test_plan_author_review_failures",
    "test_plan_author_gate_failures",
    "test_execution_review_failures",
    "max_test_plan_review_failures",
    "max_test_result_review_failures",
    "author_constraints",
    "changed_required_files",
    "control_files",
    "gate_violations",
    "last_reviewer_node",
    "stop_reason",
}


class ContractViolation(RuntimeError):
    """A fail-closed LangGraph contract violation."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def strict_json_object(text: str, *, source: str) -> dict[str, Any]:
    """Parse a pure JSON object. No markdown fences, comments, or trailing text."""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ContractViolation(f"{source} did not return pure JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ContractViolation(f"{source} returned JSON {type(payload).__name__}, expected object")
    return payload


def validate_agent_output(node_input: State, node_output: dict[str, Any], *, node_name: str) -> None:
    """Reject attempts by an LLM node to write graph/reviewer authority fields."""
    protected = sorted(PROTECTED_AGENT_OUTPUT_FIELDS & set(node_output))
    if protected:
        raise ContractViolation(
            f"node {node_name} attempted to write protected field(s): {protected}"
        )

    unknown = sorted(set(node_output) - AGENT_WRITABLE_OUTPUT_FIELDS)
    if unknown:
        raise ContractViolation(
            f"node {node_name} returned unsupported field(s): {unknown}; "
            "write control data to JSON files instead"
        )

    if "status" in node_output and not isinstance(node_output["status"], bool):
        raise ContractViolation(f"node {node_name} returned non-boolean status")

    if "artifact_path" in node_output:
        expected = str(artifact_dir(node_input))
        actual = str(Path(str(node_output["artifact_path"])).expanduser())
        if not Path(actual).is_absolute():
            actual = str(Path(actual).resolve())
        if actual != expected:
            raise ContractViolation(
                f"node {node_name} attempted to change artifact_path: {actual} != {expected}"
            )


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def load_json_file(path: Path) -> Any:
    if not path.exists():
        raise ContractViolation(f"required JSON file missing: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ContractViolation(f"invalid JSON file: {path}: {exc.msg}") from exc


def load_optional_json_file(path: Path) -> Any | None:
    if not path.exists():
        return None
    return load_json_file(path)


def write_json_file(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def artifact_dir(state: State) -> Path:
    artifact_path = state.get("artifact_path")
    if not isinstance(artifact_path, str) or not artifact_path.strip():
        raise ContractViolation("artifact_path is required")
    path = Path(artifact_path).expanduser()
    if not path.is_absolute():
        path = path.resolve()
    path.mkdir(parents=True, exist_ok=True)
    if not path.is_dir():
        raise ContractViolation(f"artifact_path is not a directory: {path}")
    return path


def as_bool(value: Any) -> bool:
    return value is True


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def blocker_identity(blocker: dict[str, Any]) -> str:
    explicit = blocker.get("blocker_id") or blocker.get("id") or blocker.get("stable_id")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    identity_material = {
        "requirement_id": blocker.get("requirement_id"),
        "severity": blocker.get("severity"),
        "finding": blocker.get("finding") or blocker.get("summary") or blocker.get("description"),
        "required_change": blocker.get("required_change"),
        "required_files": blocker.get("required_files"),
        "forbidden_substitute": blocker.get("forbidden_substitute"),
    }
    digest = hashlib.sha256(canonical_json(identity_material).encode("utf-8")).hexdigest()[:16]
    return f"BLOCKER-{digest}"


def normalize_blocker(raw: Any, *, source_node: str, default_severity: str = "P0") -> dict[str, Any]:
    if isinstance(raw, str):
        blocker: dict[str, Any] = {"finding": raw}
    elif isinstance(raw, dict):
        blocker = dict(raw)
    else:
        blocker = {"finding": repr(raw)}

    stable_id = blocker_identity(blocker)
    required_files = [
        str(item)
        for item in as_list(blocker.get("required_files"))
        if isinstance(item, (str, int, float)) and str(item).strip()
    ]
    forbidden_substitute = [
        str(item)
        for item in as_list(blocker.get("forbidden_substitute") or blocker.get("forbidden_substitutes"))
        if isinstance(item, (str, int, float)) and str(item).strip()
    ]
    evidence_atoms = [
        str(item)
        for item in as_list(blocker.get("evidence_atoms") or blocker.get("required_evidence"))
        if isinstance(item, (str, int, float)) and str(item).strip()
    ]

    normalized = {
        "blocker_id": stable_id,
        "stable_id": stable_id,
        "source_node": source_node,
        "severity": str(blocker.get("severity") or default_severity),
        "requirement_id": blocker.get("requirement_id"),
        "finding": blocker.get("finding") or blocker.get("summary") or blocker.get("description") or "unspecified blocker",
        "required_files": required_files,
        "required_change": blocker.get("required_change"),
        "forbidden_substitute": forbidden_substitute,
        "evidence_atoms": evidence_atoms,
        "status": "open",
    }
    for key in ("origin", "test_id", "priority", "rationale"):
        if key in blocker:
            normalized[key] = blocker[key]
    return normalized


def extract_blockers(payload: Any, *, source_node: str) -> list[dict[str, Any]]:
    if payload is None:
        return []
    if isinstance(payload, list):
        raw_blockers = payload
    elif isinstance(payload, dict):
        raw_blockers = (
            payload.get("open_blockers")
            or payload.get("blockers")
            or payload.get("blocking_findings")
            or payload.get("failed_requirements")
            or []
        )
    else:
        raw_blockers = []
    return [normalize_blocker(item, source_node=source_node) for item in as_list(raw_blockers)]


def dedupe_blockers(blockers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for blocker in blockers:
        deduped[blocker["stable_id"]] = blocker
    return list(deduped.values())


def file_hash(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def snapshot_files(root: Path, relative_paths: list[str]) -> dict[str, str | None]:
    return {rel: file_hash(root / rel) for rel in sorted(set(relative_paths))}


def changed_files(before: dict[str, str | None], after: dict[str, str | None]) -> list[str]:
    return [rel for rel in sorted(set(before) | set(after)) if before.get(rel) != after.get(rel)]


def required_files_from_blockers(blockers: list[dict[str, Any]]) -> list[str]:
    required: list[str] = []
    for blocker in blockers:
        for rel in blocker.get("required_files") or []:
            if isinstance(rel, str) and rel.strip():
                required.append(rel.strip())
    if not required:
        return list(DEFAULT_TEST_PLAN_REQUIRED_FILES)
    return sorted(set(required))


def review_result_payload(root: Path, node_name: str) -> tuple[dict[str, Any], list[dict[str, Any]], Path, Path, Path]:
    if node_name == NODE_B:
        result_path = root / TEST_PLAN_REVIEW_RESULT
        blockers_path = root / TEST_PLAN_REVIEW_BLOCKERS
        closure_path = root / TEST_PLAN_BLOCKER_CLOSURE
    elif node_name == NODE_D:
        result_path = root / TEST_RESULT_REVIEW_RESULT
        blockers_path = root / TEST_RESULT_REVIEW_BLOCKERS
        closure_path = root / TEST_RESULT_BLOCKER_CLOSURE
    else:
        raise ContractViolation(f"node {node_name} is not a reviewer node")

    result = load_json_file(result_path)
    if not isinstance(result, dict):
        raise ContractViolation(f"{result_path.name} must be a JSON object")
    blockers_file_payload = load_optional_json_file(blockers_path)
    blockers = dedupe_blockers(
        extract_blockers(result, source_node=node_name)
        + extract_blockers(blockers_file_payload, source_node=node_name)
    )
    return result, blockers, result_path, blockers_path, closure_path


def score_from(result: dict[str, Any], node_output: dict[str, Any]) -> int | None:
    score = result.get("score", node_output.get("score"))
    if score is None:
        return None
    if isinstance(score, bool):
        return None
    try:
        return int(score)
    except (TypeError, ValueError):
        return None


def raw_status_from(result: dict[str, Any], node_output: dict[str, Any]) -> bool:
    if "status" in result:
        return as_bool(result.get("status"))
    if "status_decision" in result:
        return as_bool(result.get("status_decision"))
    return as_bool(node_output.get("status"))


def closure_ids(root: Path, closure_path: Path) -> set[str]:
    closure = load_json_file(closure_path)
    if not isinstance(closure, dict):
        raise ContractViolation(f"{closure_path.name} must be a JSON object")
    ids = closure.get("closed_blocker_ids") or closure.get("closed_blocks") or []
    if not isinstance(ids, list):
        raise ContractViolation(f"{closure_path.name}.closed_blocker_ids must be a list")
    return {str(item) for item in ids if isinstance(item, (str, int, float)) and str(item).strip()}


def increment_blocker_counts(state: State, blockers: list[dict[str, Any]]) -> dict[str, int]:
    counts = dict(state.get("same_blocker_counts") or {})
    for blocker in blockers:
        stable_id = blocker["stable_id"]
        counts[stable_id] = int(counts.get(stable_id, 0)) + 1
    return counts


def append_blocker_history(state: State, blockers: list[dict[str, Any]], *, node_name: str) -> list[dict[str, Any]]:
    history = list(state.get("blocker_history") or [])
    timestamp = utc_now()
    for blocker in blockers:
        history.append(
            {
                "time": timestamp,
                "source_node": node_name,
                "blocker_id": blocker["blocker_id"],
                "stable_id": blocker["stable_id"],
                "severity": blocker.get("severity"),
                "requirement_id": blocker.get("requirement_id"),
                "finding": blocker.get("finding"),
            }
        )
    return history[-200:]


def author_constraints(state: State) -> dict[str, Any]:
    counts = dict(state.get("same_blocker_counts") or {})
    max_same = max([int(v) for v in counts.values()] or [0])
    failures = int(state.get("test_plan_author_review_failures") or 0)
    max_failures = int(state.get("max_test_plan_review_failures") or DEFAULT_MAX_REVIEW_FAILURES)
    remaining = max(max_failures - failures, 0)
    return {
        "json_first_entry": True,
        "cannot_close_blockers": True,
        "cannot_claim_pass": True,
        "forbid_argument_only_resolution": max_same >= 2,
        "must_rebuild_from_blocker_contract": max_same >= 3,
        "required_patch_claim_file": AUTHOR_PATCH_CLAIM,
        "remaining_test_plan_review_attempts": remaining,
        "max_test_plan_review_failures": max_failures,
    }


def base_gate_result(node_name: str, route: str, status: bool, violations: list[str]) -> dict[str, Any]:
    return {
        "time": utc_now(),
        "node": node_name,
        "route": route,
        "status": status,
        "violations": violations,
    }


def fail_state(
    node_input: State,
    node_name: str,
    *,
    reason: str,
    route: str = ROUTE_END,
    extra: dict[str, Any] | None = None,
) -> State:
    state = dict(node_input)
    violations = list(state.get("gate_violations") or [])
    violations.append(reason)
    state.update(
        {
            "current_node": node_name,
            "status": False,
            "gate_status": False,
            "gate_route": route,
            "stop_reason": reason if route == ROUTE_END else state.get("stop_reason"),
            "gate_violations": violations,
            "control_files": CONTROL_FILES,
            "author_constraints": author_constraints(state),
        }
    )
    if extra:
        state.update(extra)
    try:
        root = artifact_dir(state)
        gate = base_gate_result(node_name, route, False, [reason])
        write_json_file(root / GRAPH_GATE_RESULT, gate)
        write_json_file(root / GRAPH_STATE_SNAPSHOT, state)
    except Exception:
        pass
    return state


def validate_author_claim(root: Path, state: State, before_hashes: dict[str, str | None]) -> tuple[list[str], list[str]]:
    violations: list[str] = []
    previous_blockers = [b for b in as_list(state.get("open_blockers")) if isinstance(b, dict)]
    if not previous_blockers:
        if not (root / "TEST_PLAN.md").exists():
            violations.append("TEST_PLAN.md missing after TEST_PLAN_AUTHOR")
        return violations, []

    required = required_files_from_blockers(previous_blockers)
    after_hashes = snapshot_files(root, required)
    changed = changed_files(before_hashes, after_hashes)
    missing_diff = [rel for rel in required if rel not in changed]
    if missing_diff:
        violations.append(f"required_files missing substantive diff: {missing_diff}")

    claim_path = root / AUTHOR_PATCH_CLAIM
    claim = load_optional_json_file(claim_path)
    if not isinstance(claim, dict):
        violations.append(f"{AUTHOR_PATCH_CLAIM} missing or not a JSON object")
        return violations, changed

    resolution_type = str(claim.get("resolution_type") or claim.get("claim_type") or "").lower()
    forbidden_types = {"argument_only", "reinterpretation", "traceability_only", "reuse_old_tp", "documentation_only"}
    if resolution_type in forbidden_types:
        violations.append(f"forbidden author resolution_type: {resolution_type}")

    claims = claim.get("blocker_claims") or claim.get("claims") or []
    if not isinstance(claims, list):
        violations.append(f"{AUTHOR_PATCH_CLAIM}.blocker_claims must be a list")
        return violations, changed
    by_id: dict[str, dict[str, Any]] = {}
    for item in claims:
        if isinstance(item, dict):
            bid = item.get("blocker_id") or item.get("stable_id") or item.get("id")
            if isinstance(bid, str) and bid.strip():
                by_id[bid.strip()] = item

    for blocker in previous_blockers:
        bid = str(blocker.get("stable_id") or blocker.get("blocker_id"))
        item = by_id.get(bid) or by_id.get(str(blocker.get("blocker_id")))
        if not item:
            violations.append(f"{AUTHOR_PATCH_CLAIM} missing claim for blocker {bid}")
            continue
        modified = [str(x) for x in as_list(item.get("modified_files")) if str(x).strip()]
        test_ids = [str(x) for x in as_list(item.get("new_or_modified_test_ids") or item.get("test_ids")) if str(x).strip()]
        evidence = as_list(item.get("evidence_contract") or item.get("evidence_atoms"))
        if not set(modified) & set(blocker.get("required_files") or required):
            violations.append(f"claim for blocker {bid} does not modify required files")
        if not test_ids:
            violations.append(f"claim for blocker {bid} has no new_or_modified_test_ids")
        if not evidence:
            violations.append(f"claim for blocker {bid} has no evidence_contract")

    return violations, changed


def gate_author(
    node_input: State,
    node_output: dict[str, Any],
    *,
    before_hashes: dict[str, str | None],
) -> State:
    state = {**node_input, **node_output}
    root = artifact_dir(state)
    raw_status = as_bool(node_output.get("status"))
    violations: list[str] = []
    changed: list[str] = []

    if not raw_status:
        violations.append("TEST_PLAN_AUTHOR returned status=false")
    else:
        claim_violations, changed = validate_author_claim(root, state, before_hashes)
        violations.extend(claim_violations)

    gate_status = not violations
    if gate_status:
        route = NODE_B
        stop_reason = state.get("stop_reason")
    else:
        failures = int(state.get("test_plan_author_gate_failures") or 0) + 1
        state["test_plan_author_gate_failures"] = failures
        max_failures = int(state.get("max_test_plan_review_failures") or DEFAULT_MAX_REVIEW_FAILURES)
        if failures >= max_failures:
            route = ROUTE_END
            stop_reason = f"test_plan_author_gate_failures reached {failures}/{max_failures}; developer intervention required"
            violations.append(stop_reason)
        else:
            route = NODE_A
            stop_reason = "; ".join(violations)
    workflow_status = False if state.get("open_blockers") else gate_status
    state.update(
        {
            "current_node": NODE_A,
            "raw_status": raw_status,
            "status": workflow_status,
            "gate_status": gate_status,
            "gate_route": route,
            "changed_required_files": changed,
            "control_files": CONTROL_FILES,
            "author_constraints": author_constraints(state),
            "gate_violations": violations,
            "stop_reason": stop_reason,
        }
    )
    write_gate_files(root, state, NODE_A, route, gate_status, violations)
    return state


def gate_reviewer(node_input: State, node_output: dict[str, Any], *, node_name: str) -> State:
    state = {**node_input, **node_output}
    root = artifact_dir(state)
    violations: list[str] = []

    try:
        result, blockers, result_path, blockers_path, closure_path = review_result_payload(root, node_name)
    except ContractViolation as exc:
        return fail_state(state, node_name, reason=str(exc), route=ROUTE_END)

    score = score_from(result, node_output)
    raw_status = raw_status_from(result, node_output)
    threshold = int(state.get("review_pass_score") or DEFAULT_SCORE_THRESHOLD)
    previous_blockers = [b for b in as_list(node_input.get("open_blockers")) if isinstance(b, dict)]

    if not blockers_path.exists():
        return fail_state(state, node_name, reason=f"{blockers_path.name} missing", route=ROUTE_END)
    if score is None:
        return fail_state(state, node_name, reason=f"{result_path.name} missing integer score", route=ROUTE_END)
    if score < threshold and raw_status:
        return fail_state(
            state,
            node_name,
            reason=f"score {score} below threshold {threshold} but status=true",
            route=ROUTE_END,
        )
    if blockers and raw_status:
        return fail_state(
            state,
            node_name,
            reason="open_blockers present but reviewer status=true",
            route=ROUTE_END,
            extra={"open_blockers": blockers, "review_score": score, "effective_score": 0},
        )
    if not raw_status and not blockers:
        return fail_state(state, node_name, reason="reviewer status=false but no open blockers were written", route=ROUTE_END)
    if score < threshold and not blockers:
        return fail_state(
            state,
            node_name,
            reason=f"score {score} below threshold {threshold} but no open blockers were written",
            route=ROUTE_END,
        )

    malformed_p0 = [
        blocker["blocker_id"]
        for blocker in blockers
        if str(blocker.get("severity", "")).upper() == "P0"
        and not blocker.get("required_files")
    ]
    if malformed_p0:
        return fail_state(
            state,
            node_name,
            reason=f"P0 blocker(s) missing required_files: {malformed_p0}",
            route=ROUTE_END,
        )

    passed = not violations and raw_status and not blockers and score >= threshold

    if passed and previous_blockers:
        try:
            closed_ids = closure_ids(root, closure_path)
        except ContractViolation as exc:
            previous_ids = sorted(
                str(blocker.get("stable_id") or blocker.get("blocker_id"))
                for blocker in previous_blockers
            )
            return fail_state(
                state,
                node_name,
                reason=f"{closure_path.name} missing closures for previous blockers: {previous_ids}; {exc}",
                route=ROUTE_END,
            )
        missing = {
            str(blocker.get("stable_id") or blocker.get("blocker_id"))
            for blocker in previous_blockers
        } - closed_ids
        if missing:
            return fail_state(
                state,
                node_name,
                reason=f"{closure_path.name} missing closures for blockers: {sorted(missing)}",
                route=ROUTE_END,
            )

    if node_name == NODE_B:
        failure_counter_name = "test_plan_author_review_failures"
        fail_route = NODE_A
        pass_route = NODE_C
        max_failures = int(state.get("max_test_plan_review_failures") or DEFAULT_MAX_REVIEW_FAILURES)
    else:
        failure_counter_name = "test_execution_review_failures"
        fail_route = NODE_C
        pass_route = NODE_E
        max_failures = int(state.get("max_test_result_review_failures") or DEFAULT_MAX_REVIEW_FAILURES)

    if passed:
        route = pass_route
        open_blockers: list[dict[str, Any]] = []
        gate_status = True
        effective_score = score
        stop_reason = None
    else:
        route = fail_route
        open_blockers = blockers
        gate_status = False
        effective_score = 0 if any(str(b.get("severity", "")).upper() == "P0" for b in blockers) else (score or 0)
        failures = int(state.get(failure_counter_name) or 0) + 1
        state[failure_counter_name] = failures
        if failures >= max_failures:
            route = ROUTE_END
            stop_reason = f"{failure_counter_name} reached {failures}/{max_failures}; developer intervention required"
            violations.append(stop_reason)
        else:
            stop_reason = "; ".join(violations) if violations else None

    counts = increment_blocker_counts(state, open_blockers) if open_blockers else dict(state.get("same_blocker_counts") or {})
    history = append_blocker_history(state, open_blockers, node_name=node_name) if open_blockers else list(state.get("blocker_history") or [])
    state.update(
        {
            "current_node": node_name,
            "raw_status": raw_status,
            "status": gate_status,
            "gate_status": gate_status,
            "gate_route": route,
            "review_score": score,
            "effective_score": effective_score,
            "open_blockers": open_blockers,
            "same_blocker_counts": counts,
            "blocker_history": history,
            "control_files": CONTROL_FILES,
            "author_constraints": author_constraints(state),
            "gate_violations": violations,
            "last_reviewer_node": node_name,
            "stop_reason": stop_reason,
        }
    )
    write_gate_files(root, state, node_name, route, gate_status, violations)
    return state


def gate_executor(node_input: State, node_output: dict[str, Any]) -> State:
    state = {**node_input, **node_output}
    root = artifact_dir(state)
    raw_status = as_bool(node_output.get("status"))
    violations: list[str] = []
    if not raw_status:
        violations.append("TEST_EXECUTOR returned status=false")
    if raw_status and not (root / "execution_report.md").exists():
        violations.append("execution_report.md missing after TEST_EXECUTOR")
    if raw_status and not (root / TEST_EXECUTION_CLAIM).exists():
        violations.append(f"{TEST_EXECUTION_CLAIM} missing after TEST_EXECUTOR")
    route = NODE_D if not violations else ROUTE_END
    gate_status = not violations
    state.update(
        {
            "current_node": NODE_C,
            "raw_status": raw_status,
            "status": gate_status,
            "gate_status": gate_status,
            "gate_route": route,
            "control_files": CONTROL_FILES,
            "author_constraints": author_constraints(state),
            "gate_violations": violations,
            "stop_reason": "; ".join(violations) if violations else state.get("stop_reason"),
        }
    )
    write_gate_files(root, state, NODE_C, route, gate_status, violations)
    return state


def gate_report_writer(node_input: State, node_output: dict[str, Any]) -> State:
    state = {**node_input, **node_output}
    root = artifact_dir(state)
    raw_status = as_bool(node_output.get("status"))
    violations: list[str] = []
    if not raw_status:
        violations.append("TEST_REPORT_WRITER returned status=false")
    if raw_status and not (root / "TEST_REPORT.md").exists():
        violations.append("TEST_REPORT.md missing after TEST_REPORT_WRITER")
    route = NODE_F if not violations else ROUTE_END
    gate_status = not violations
    state.update(
        {
            "current_node": NODE_E,
            "raw_status": raw_status,
            "status": gate_status,
            "gate_status": gate_status,
            "gate_route": route,
            "control_files": CONTROL_FILES,
            "author_constraints": author_constraints(state),
            "gate_violations": violations,
            "stop_reason": "; ".join(violations) if violations else state.get("stop_reason"),
        }
    )
    write_gate_files(root, state, NODE_E, route, gate_status, violations)
    return state


def gate_final_reviewer(node_input: State, node_output: dict[str, Any]) -> State:
    state = {**node_input, **node_output}
    root = artifact_dir(state)
    raw_status = as_bool(node_output.get("status"))
    violations: list[str] = []
    if not raw_status:
        violations.append("FINAL_REVIEWER returned status=false")
    if raw_status and not (root / "FINAL_REVIEW.md").exists():
        violations.append("FINAL_REVIEW.md missing after FINAL_REVIEWER")
    route = ROUTE_END
    gate_status = not violations
    state.update(
        {
            "current_node": NODE_F,
            "raw_status": raw_status,
            "status": gate_status,
            "gate_status": gate_status,
            "gate_route": route,
            "control_files": CONTROL_FILES,
            "author_constraints": author_constraints(state),
            "gate_violations": violations,
            "stop_reason": "; ".join(violations) if violations else state.get("stop_reason"),
        }
    )
    write_gate_files(root, state, NODE_F, route, gate_status, violations)
    return state


def write_gate_files(root: Path, state: State, node_name: str, route: str, status: bool, violations: list[str]) -> None:
    gate = base_gate_result(node_name, route, status, violations)
    gate.update(
        {
            "raw_status": state.get("raw_status"),
            "review_score": state.get("review_score"),
            "effective_score": state.get("effective_score"),
            "open_blockers": state.get("open_blockers", []),
            "same_blocker_counts": state.get("same_blocker_counts", {}),
            "test_plan_author_review_failures": state.get("test_plan_author_review_failures", 0),
            "test_plan_author_gate_failures": state.get("test_plan_author_gate_failures", 0),
            "stop_reason": state.get("stop_reason"),
        }
    )
    write_json_file(root / GRAPH_GATE_RESULT, gate)
    write_json_file(root / GRAPH_STATE_SNAPSHOT, state)


def put_default_if_none(state: State, key: str, value: Any) -> None:
    if state.get(key) is None:
        state[key] = value


def prepare_node_input(state: State, *, node_name: str) -> State:
    prepared = dict(state)
    prepared["current_node"] = node_name
    put_default_if_none(prepared, "control_files", CONTROL_FILES)
    put_default_if_none(prepared, "open_blockers", [])
    put_default_if_none(prepared, "blocker_history", [])
    put_default_if_none(prepared, "same_blocker_counts", {})
    put_default_if_none(prepared, "test_plan_author_review_failures", 0)
    put_default_if_none(prepared, "test_plan_author_gate_failures", 0)
    put_default_if_none(prepared, "test_execution_review_failures", 0)
    put_default_if_none(prepared, "max_test_plan_review_failures", DEFAULT_MAX_REVIEW_FAILURES)
    put_default_if_none(prepared, "max_test_result_review_failures", DEFAULT_MAX_REVIEW_FAILURES)
    put_default_if_none(prepared, "review_pass_score", DEFAULT_SCORE_THRESHOLD)
    prepared["author_constraints"] = author_constraints(prepared)
    return prepared


def before_author_hashes(state: State) -> dict[str, str | None]:
    root = artifact_dir(state)
    blockers = [b for b in as_list(state.get("open_blockers")) if isinstance(b, dict)]
    required = required_files_from_blockers(blockers) if blockers else ["TEST_PLAN.md"]
    return snapshot_files(root, required)
