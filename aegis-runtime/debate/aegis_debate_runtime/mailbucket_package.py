from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any


class DebateMailbucketPackageError(ValueError):
    """Raised when the Debate result mailbucket package is incomplete."""


REQUIRED_PACKAGE_FILES = (
    "README.md",
    "final_report.json",
    "adjudicator_causal_state.json",
    "transcript_digest.json",
    "evidence_manifest.json",
)


def write_debate_result_mailbucket_package(
    *,
    output_dir: str | Path,
    final_report: dict[str, Any],
    adjudicator_causal_state: dict[str, Any],
    worker_states: list[dict[str, Any]],
    worker_proofs: list[dict[str, Any]] | None = None,
    worker_proof_paths: list[str | Path] | None = None,
    transcript_digest: list[dict[str, Any]] | None = None,
    evidence_manifest: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if worker_proofs and worker_proof_paths:
        raise DebateMailbucketPackageError("pass either worker_proofs or worker_proof_paths, not both")

    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    worker_state_dir = root / "worker_states"
    worker_proof_dir = root / "worker_proofs"
    worker_state_dir.mkdir(exist_ok=True)
    worker_proof_dir.mkdir(exist_ok=True)

    run_id = str(final_report.get("run_id") or adjudicator_causal_state.get("run_id") or "unknown_run")
    decision = final_report.get("decision")
    developer_required = bool(
        final_report.get("developer_decision_required")
        or final_report.get("causal_result", {}).get("developer_decision_required", False)
    )

    _write_json(root / "final_report.json", final_report)
    _write_json(root / "adjudicator_causal_state.json", adjudicator_causal_state)
    _write_json(root / "transcript_digest.json", transcript_digest or final_report.get("transcript_digest", []))
    _write_json(root / "evidence_manifest.json", evidence_manifest or _evidence_manifest(final_report, worker_states))

    state_files: list[str] = []
    for state in worker_states:
        worker_id = str(state.get("worker_id") or state.get("agent_id") or state.get("stance_id") or "worker")
        path = worker_state_dir / f"{_safe_name(worker_id)}.json"
        _write_json(path, state)
        state_files.append(str(path.relative_to(root)))

    proof_files: list[str] = []
    if worker_proof_paths:
        for proof_path in worker_proof_paths:
            src = Path(proof_path)
            if not src.is_file():
                raise DebateMailbucketPackageError(f"worker proof does not exist: {src}")
            dst = worker_proof_dir / src.name
            shutil.copyfile(src, dst)
            if _sha256_file(src) != _sha256_file(dst):
                raise DebateMailbucketPackageError(f"worker proof copy hash mismatch: {src} -> {dst}")
            proof_files.append(str(dst.relative_to(root)))
    else:
        for proof in worker_proofs or []:
            worker_id = str(proof.get("worker_id") or proof.get("agent_id") or proof.get("stance_id") or "worker")
            path = worker_proof_dir / f"{_safe_name(worker_id)}_proof.json"
            _write_json(path, proof)
            proof_files.append(str(path.relative_to(root)))

    readme = _make_readme(
        run_id=run_id,
        decision=str(decision),
        developer_decision_required=developer_required,
        state_files=state_files,
        proof_files=proof_files,
    )
    (root / "README.md").write_text(readme, encoding="utf-8")

    validate_debate_result_mailbucket_package(
        root,
        require_worker_proofs=bool(worker_proofs) or bool(worker_proof_paths),
    )
    return {
        "package_dir": str(root),
        "run_id": run_id,
        "decision": decision,
        "developer_decision_required": developer_required,
        "worker_state_count": len(state_files),
        "worker_proof_count": len(proof_files),
    }


def copy_existing_worker_proofs(*, proof_paths: list[str | Path], package_dir: str | Path) -> list[dict[str, Any]]:
    root = Path(package_dir) / "worker_proofs"
    root.mkdir(parents=True, exist_ok=True)
    copied: list[dict[str, Any]] = []
    for proof_path in proof_paths:
        src = Path(proof_path)
        if not src.is_file():
            raise DebateMailbucketPackageError(f"worker proof does not exist: {src}")
        dst = root / src.name
        shutil.copyfile(src, dst)
        copied.append({"source": str(src), "package_path": str(dst)})
    return copied


def validate_debate_result_mailbucket_package(
    package_dir: str | Path,
    *,
    require_worker_proofs: bool = True,
) -> None:
    root = Path(package_dir)
    if not root.is_dir():
        raise DebateMailbucketPackageError(f"package directory does not exist: {root}")
    missing = [name for name in REQUIRED_PACKAGE_FILES if not (root / name).is_file()]
    if missing:
        raise DebateMailbucketPackageError(f"package missing required file(s): {', '.join(missing)}")
    worker_states = list((root / "worker_states").glob("*.json")) if (root / "worker_states").is_dir() else []
    if not worker_states:
        raise DebateMailbucketPackageError("package must contain at least one worker state")
    if require_worker_proofs:
        worker_proofs = list((root / "worker_proofs").glob("*_proof.json")) if (root / "worker_proofs").is_dir() else []
        if len(worker_proofs) < len(worker_states):
            raise DebateMailbucketPackageError("each worker state requires a matching real nested-Codex worker proof")


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _safe_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in value)


def _make_readme(
    *,
    run_id: str,
    decision: str,
    developer_decision_required: bool,
    state_files: list[str],
    proof_files: list[str],
) -> str:
    return f"""# Debate Result Mailbucket Package

run_id: `{run_id}`

decision: `{decision}`

developer_decision_required: `{str(developer_decision_required).lower()}`

## Contents

- `final_report.json` — Debate Leader final causal report.
- `adjudicator_causal_state.json` — Leader causal state with route and expand priorities.
- `worker_states/` — Worker-local causal states.
- `worker_proofs/` — Real nested-Codex worker creation proofs.
- `transcript_digest.json` — Structured digest of debate turns.
- `evidence_manifest.json` — Evidence references used by the run.

## Worker states

{chr(10).join(f'- `{item}`' for item in state_files) or '- none'}

## Worker proofs

{chr(10).join(f'- `{item}`' for item in proof_files) or '- none'}

## Boundary

This folder is a mailbucket delivery package. The router must not interpret its semantics.

Master reads this package and decides whether to merge, request tests, reject, or ask the developer to choose when developer decision is required.
"""


def _evidence_manifest(final_report: dict[str, Any], worker_states: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    causal_result = final_report.get("causal_result")
    if isinstance(causal_result, dict):
        for item in causal_result.get("evidence", []) or []:
            if isinstance(item, dict):
                result.append(dict(item))
    for state in worker_states:
        for item in state.get("evidence", []) or []:
            if isinstance(item, dict):
                result.append(dict(item))
    return result
