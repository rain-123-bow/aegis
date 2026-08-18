from __future__ import annotations

import json
import hashlib
import subprocess
import shutil
from functools import lru_cache
import sys
from pathlib import Path


SCOPE_POLICY_RELATIVE_PATH = Path(
    ".aegis/reasoning_ledger/artifacts/facts/runtime-behavior-scope.json"
)
SCOPE_REVIEW_RELATIVE_PATH = Path(
    ".aegis/reasoning_ledger/artifacts/reviews/runtime-behavior-scope-review.md"
)
SCOPE_REVIEW_RESULT_RELATIVE_PATH = Path(
    ".aegis/reasoning_ledger/artifacts/reviews/runtime-behavior-scope-review.json"
)
SCOPE_USER_CONFIRMATION_RELATIVE_PATH = Path(
    ".aegis/reasoning_ledger/artifacts/facts/runtime-behavior-scope-user-confirmation.json"
)
SCOPE_DECISION_RELATIVE_PATH = Path(
    ".aegis/reasoning_ledger/artifacts/facts/runtime-behavior-scope-decision.json"
)


@lru_cache(maxsize=1)
def _test_git_pins() -> tuple[str, str]:
    from runtime_identity import git_runtime_manifest

    git = Path(shutil.which("git") or "")
    launcher_sha256 = hashlib.sha256(git.read_bytes()).hexdigest()
    _files, runtime_sha256 = git_runtime_manifest(git)
    return launcher_sha256, runtime_sha256


def initialize_test_git_repository(project: Path, message: str = "fixture") -> str:
    project.mkdir(parents=True, exist_ok=True)
    commands = [
        ["git", "-C", str(project), "init"],
        ["git", "-C", str(project), "config", "core.autocrlf", "false"],
        ["git", "-C", str(project), "add", "--all"],
        [
            "git",
            "-C",
            str(project),
            "-c",
            "user.name=Aegis Test",
            "-c",
            "user.email=aegis@example.invalid",
            "commit",
            "-m",
            message,
        ],
        ["git", "-C", str(project), "rev-parse", "HEAD"],
    ]
    head = ""
    for command in commands:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f"test Git fixture failed: {command!r}: {completed.stderr!r}"
            )
        head = completed.stdout.strip() or head
    return head


def write_test_runtime_scope_policy(
    project: Path,
    *,
    project_id: bytes = bytes(range(16)),
) -> Path:
    review_path = project / SCOPE_REVIEW_RELATIVE_PATH
    review_result_path = project / SCOPE_REVIEW_RESULT_RELATIVE_PATH
    confirmation_path = project / SCOPE_USER_CONFIRMATION_RELATIVE_PATH
    review_path.parent.mkdir(parents=True, exist_ok=True)
    confirmation_path.parent.mkdir(parents=True, exist_ok=True)
    review_path.write_text("# Runtime scope review\n\nPASS\n", encoding="utf-8")
    review_bytes = review_path.read_bytes()
    include_roots = [
        name
        for name in (
            "src",
            "config",
            "third_party/TraceRelay/src/tracerelay",
            "third_party/AegisSealCore/windows-x64",
        )
        if (project / name).is_dir()
    ]
    include_files = [
        name
        for name in (
            "pyproject.toml",
            "CMakeLists.txt",
            "requirements-runtime.txt",
            "third_party/TraceRelay/PROVENANCE.json",
        )
        if (project / name).is_file()
    ]
    path = project / SCOPE_POLICY_RELATIVE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "aegis.runtime_behavior_scope_definition.v1",
        "project_id_hex": project_id.hex(),
        "version": 1,
        "include_roots": include_roots,
        "include_files": include_files,
        "exclude_roots": ["test", "tests", "demo", "demos"],
        "exclude_files": [],
        "force_include_files": [],
        "external_tools": {
            "git_sha256": _test_git_pins()[0],
            "git_runtime_sha256": _test_git_pins()[1],
        },
        "runtime_authority_id": "ab" * 16,
    }
    policy_bytes = _canonical_json_bytes(payload)
    path.write_bytes(policy_bytes)
    policy_sha256 = hashlib.sha256(policy_bytes).hexdigest()
    review_result = {
        "schema": "aegis.runtime_behavior_scope_review.v1",
        "review_id": "unit-test-review",
        "project_id_hex": project_id.hex(),
        "scope_definition_sha256": policy_sha256,
        "verdict": "PASS",
        "report": _descriptor(SCOPE_REVIEW_RELATIVE_PATH, review_bytes),
    }
    review_result_bytes = _canonical_json_bytes(review_result)
    review_result_path.write_bytes(review_result_bytes)
    confirmation = {
        "schema": "aegis.runtime_behavior_scope_user_confirmation.v1",
        "confirmation_id": "unit-test-fixture",
        "project_id_hex": project_id.hex(),
        "scope_definition_sha256": policy_sha256,
        "review_result": _descriptor(
            SCOPE_REVIEW_RESULT_RELATIVE_PATH, review_result_bytes
        ),
        "decision": "CONFIRMED",
        "statement": "I confirm this exact runtime behavior scope and PASS review.",
    }
    confirmation_bytes = _canonical_json_bytes(confirmation)
    confirmation_path.write_bytes(confirmation_bytes)
    decision_path = project / SCOPE_DECISION_RELATIVE_PATH
    decision_path.write_bytes(
        _canonical_json_bytes(
            {
                "schema": "aegis.runtime_behavior_scope_decision.v3",
                "project_id_hex": project_id.hex(),
                "decision": "APPROVED",
                "scope_definition": _descriptor(
                    SCOPE_POLICY_RELATIVE_PATH, policy_bytes
                ),
                "review_result": _descriptor(
                    SCOPE_REVIEW_RESULT_RELATIVE_PATH, review_result_bytes
                ),
                "user_confirmation": {
                    **_descriptor(
                        SCOPE_USER_CONFIRMATION_RELATIVE_PATH,
                        confirmation_bytes,
                    ),
                    "confirmation_id": "unit-test-fixture",
                },
            }
        )
    )
    return path


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _descriptor(path: Path, content: bytes) -> dict[str, object]:
    return {
        "path": path.as_posix(),
        "size": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def refresh_test_runtime_scope_approvals(project: Path) -> None:
    policy_path = project / SCOPE_POLICY_RELATIVE_PATH
    policy_bytes = policy_path.read_bytes()
    policy = json.loads(policy_bytes.decode("utf-8"))
    project_id_hex = str(policy["project_id_hex"])
    policy_sha256 = hashlib.sha256(policy_bytes).hexdigest()
    review_path = project / SCOPE_REVIEW_RELATIVE_PATH
    review_bytes = review_path.read_bytes()
    review_result = {
        "schema": "aegis.runtime_behavior_scope_review.v1",
        "review_id": "unit-test-review",
        "project_id_hex": project_id_hex,
        "scope_definition_sha256": policy_sha256,
        "verdict": "PASS",
        "report": _descriptor(SCOPE_REVIEW_RELATIVE_PATH, review_bytes),
    }
    review_result_bytes = _canonical_json_bytes(review_result)
    (project / SCOPE_REVIEW_RESULT_RELATIVE_PATH).write_bytes(review_result_bytes)
    confirmation = {
        "schema": "aegis.runtime_behavior_scope_user_confirmation.v1",
        "confirmation_id": "unit-test-fixture",
        "project_id_hex": project_id_hex,
        "scope_definition_sha256": policy_sha256,
        "review_result": _descriptor(
            SCOPE_REVIEW_RESULT_RELATIVE_PATH, review_result_bytes
        ),
        "decision": "CONFIRMED",
        "statement": "I confirm this exact runtime behavior scope and PASS review.",
    }
    confirmation_bytes = _canonical_json_bytes(confirmation)
    (project / SCOPE_USER_CONFIRMATION_RELATIVE_PATH).write_bytes(
        confirmation_bytes
    )
    decision = {
        "schema": "aegis.runtime_behavior_scope_decision.v3",
        "project_id_hex": project_id_hex,
        "decision": "APPROVED",
        "scope_definition": _descriptor(
            SCOPE_POLICY_RELATIVE_PATH, policy_bytes
        ),
        "review_result": _descriptor(
            SCOPE_REVIEW_RESULT_RELATIVE_PATH, review_result_bytes
        ),
        "user_confirmation": {
            **_descriptor(
                SCOPE_USER_CONFIRMATION_RELATIVE_PATH, confirmation_bytes
            ),
            "confirmation_id": "unit-test-fixture",
        },
    }
    (project / SCOPE_DECISION_RELATIVE_PATH).write_bytes(
        _canonical_json_bytes(decision)
    )


def write_test_engineering_input_manifest(
    project: Path,
    *,
    project_id: bytes = bytes(range(16)),
) -> Path:
    requirements = project / "docs" / "REQUIREMENTS.md"
    implementation = project / "docs" / "IMPLEMENTATION_PLAN.md"
    requirements.parent.mkdir(parents=True, exist_ok=True)
    requirements.write_text("Synthetic acceptance requirement.\n", encoding="utf-8")
    implementation.write_text("Synthetic acceptance implementation.\n", encoding="utf-8")

    def descriptor(kind: str, path: Path) -> dict[str, object]:
        content = path.read_bytes()
        return {
            "kind": kind,
            "path": str(path.resolve()),
            "size": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        }

    manifest = project / "ENGINEERING_INPUT_MANIFEST.json"
    manifest.write_text(
        json.dumps(
            {
                "schema": "aegis.engineering_input_manifest.v1",
                "project_id_hex": project_id.hex(),
                "created_at_utc": "2026-08-18T00:00:00Z",
                "documents": [
                    descriptor("REQUIREMENTS", requirements),
                    descriptor("IMPLEMENTATION_PLAN", implementation),
                ],
            }
        ),
        encoding="utf-8",
    )
    return manifest


def write_test_execution_request(
    project: Path,
    artifact_root: Path,
    *,
    project_id_hex: str,
    workflow_run_id: str,
    attempt_id: str,
) -> Path:
    tests = write_test_execution_policy(project, artifact_root)
    plan = artifact_root / "APPROVED_TEST_PLAN.md"
    plan_bytes = plan.read_bytes()
    payload = {
        "schema": "aegis.test_execution_request.v3",
        "project_id_hex": project_id_hex,
        "workflow_run_id": workflow_run_id,
        "attempt_id": attempt_id,
        "approved_test_plan_sha256": hashlib.sha256(plan_bytes).hexdigest(),
        "tests": tests,
    }
    path = artifact_root / "TEST_EXECUTION_REQUEST.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def write_test_execution_policy(
    project: Path,
    artifact_root: Path,
) -> list[dict[str, object]]:
    plan = artifact_root / "APPROVED_TEST_PLAN.md"
    if plan.is_file():
        text = plan.read_text(encoding="utf-8")
        begin = "<!-- AEGIS_TEST_EXECUTION_POLICY_BEGIN -->"
        end = "<!-- AEGIS_TEST_EXECUTION_POLICY_END -->"
        if text.count(begin) == 1 and text.count(end) == 1:
            policy = json.loads(text.split(begin, 1)[1].split(end, 1)[0].strip())
            return list(policy["tests"])
    source = next(path for path in (project / "src").rglob("*") if path.is_file())
    source_bytes = source.read_bytes()
    test_root = artifact_root / "test_demos"
    test_root.mkdir(parents=True, exist_ok=True)
    entry = test_root / "pass_test.py"
    entry.write_text("print('PASS')\n", encoding="utf-8")
    entry_bytes = entry.read_bytes()
    executable = Path(sys._base_executable).resolve()
    executable_bytes = executable.read_bytes()
    plan.parent.mkdir(parents=True, exist_ok=True)
    tests = [
        {
            "test_id": "T-001",
            "requirement_ids": ["R-001"],
            "command": [str(executable), str(entry.resolve())],
            "cwd": str(project.resolve()),
            "environment": {"PYTHONDONTWRITEBYTECODE": "1"},
            "timeout_seconds": 30,
            "test_inputs": [
                {
                    "path": str(source.resolve()),
                    "size": len(source_bytes),
                    "sha256": hashlib.sha256(source_bytes).hexdigest(),
                },
                {
                    "path": str(entry.resolve()),
                    "size": len(entry_bytes),
                    "sha256": hashlib.sha256(entry_bytes).hexdigest(),
                },
            ],
            "executable": {
                "path": str(executable),
                "size": len(executable_bytes),
                "sha256": hashlib.sha256(executable_bytes).hexdigest(),
            },
        }
    ]
    policy = {"schema": "aegis.test_execution_policy.v2", "tests": tests}
    plan.write_text(
        "# approved unit-test plan\n\n"
        "<!-- AEGIS_TEST_EXECUTION_POLICY_BEGIN -->\n"
        + json.dumps(policy, ensure_ascii=False, sort_keys=True)
        + "\n<!-- AEGIS_TEST_EXECUTION_POLICY_END -->\n",
        encoding="utf-8",
    )
    return tests


def write_test_reasoning_context_pack(
    project: Path,
    output_path: Path,
    *,
    project_id_hex: str,
    project_seal: str,
    engineering_documents_sha256: str,
    task_id: str = "task-unit-test",
    agent_role: str = "AEGIS_WORKFLOW",
) -> Path:
    evidence = project / SCOPE_POLICY_RELATIVE_PATH
    if not evidence.is_file():
        raise ValueError("test context pack requires a runtime scope policy")
    evidence_bytes = evidence.read_bytes()
    relative_evidence = evidence.relative_to(project).as_posix()
    item = {
        "id": "fact.runtime.scope",
        "project_id": project_id_hex,
        "type": "fact",
        "status": "active",
        "scope": {"task": task_id},
        "content": "The runtime scope policy is frozen evidence.",
        "artifact_path": relative_evidence,
        "source": "runtime-scope-policy",
        "evidence_path": relative_evidence,
        "confidence": 1.0,
        "level": 0,
        "version": 1,
        "metadata": {},
        "created_by": "unit-test-fixture",
        "created_at": "2026-08-17T00:00:00Z",
        "updated_at": "2026-08-17T00:00:00Z",
    }
    live_snapshot = {"items": [item], "edges": [], "events": [{"id": 1}]}
    live_snapshot_bytes = json.dumps(
        live_snapshot,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    live_snapshot_path = (
        project / ".aegis" / "reasoning_ledger" / "test-live-snapshot.json"
    )
    live_snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    live_snapshot_path.write_bytes(live_snapshot_bytes)
    payload = {
        "schema": "aegis.reasoning_context_pack.v1",
        "project_id_hex": project_id_hex,
        "task_id": task_id,
        "agent_role": agent_role,
        "query": "requirements implementation plan runtime scope code causality refutations environment warnings",
        "generated_at_utc": "2026-08-17T00:00:00Z",
        "bindings": {
            "project_seal": project_seal,
            "engineering_documents_sha256": engineering_documents_sha256,
        },
        "ledger": {
            "revision": 1,
            "snapshot_sha256": hashlib.sha256(live_snapshot_bytes).hexdigest(),
        },
        "retrieval": {
            "mode": "unit_test_fixture",
            "embedding_source": "codex-gpt",
            "scope": {"task": task_id},
            "limit": 12,
            "include_causes": True,
        },
        "coverage": {
            "requirements": True,
            "implementation_plan": True,
            "runtime_scope": True,
            "code_causality": True,
            "known_refutations": True,
            "environment_facts": True,
            "pending_warnings": True,
        },
        "items": [item],
        "cause_items": [],
        "edges": [],
        "warnings": [],
        "required_artifact_paths": [relative_evidence],
        "evidence_index": [
            {
                "path": str(evidence.resolve()),
                "size": len(evidence_bytes),
                "sha256": hashlib.sha256(evidence_bytes).hexdigest(),
            }
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload), encoding="utf-8")
    return output_path
