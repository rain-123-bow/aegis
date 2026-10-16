"""Prepare exact real-test projects before freezing the user's Codex config.

The returned manifest and its SHA-256 must be bound by the external preflight.
This module is test setup, not a runtime gate or production authorization.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import tomllib
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from uuid import uuid4


CASE_DIRECTORIES = {
    "control-plane": "as_pilot",
    "hard-crash": "as_crash_recovery",
    "registration-crash": "as_registration_crash",
}
SCHEMA = "aegis.prepared_acceptance.v1"


def _descriptor(path: Path) -> dict[str, object]:
    content = path.read_bytes()
    return {"path": str(path), "size": len(content),
            "sha256": hashlib.sha256(content).hexdigest()}


def _absolute(path: str | Path) -> Path:
    path = Path(path)
    if not path.is_absolute():
        raise ValueError("acceptance preparation requires absolute paths")
    return path.resolve()


def _same_toml(left: object, right: object) -> bool:
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(
            _same_toml(value, right[key]) for key, value in left.items()
        )
    if isinstance(left, list):
        return len(left) == len(right) and all(
            _same_toml(a, b) for a, b in zip(left, right)
        )
    return left == right


def initialize_codex_project(project: Path) -> None:
    """Initialize the eventual Git root and Codex trust without a model turn."""
    from codex_app_server_client import AppServerClient

    git = shutil.which("git")
    if git is None:
        raise RuntimeError("Git is required for acceptance preparation")
    subprocess.run(
        [git, "init", str(project)], check=True, capture_output=True,
        timeout=30, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    with AppServerClient(cwd=project) as client:
        profile = client.start_thread(
            ephemeral=True, sandbox="danger-full-access", approval_policy="never",
        )
        if not profile.model or profile.reasoning_effort not in {"low", "medium", "high"}:
            raise RuntimeError("acceptance preparation requires a model with at most high effort")


def prepare_acceptance(
    root: Path,
    cases: Sequence[str],
    *,
    config_path: Path,
    initialize_project: Callable[[Path], None],
) -> Path:
    """Reserve fresh projects, initialize trust, then capture the complete config."""
    root, config_path = _absolute(root), _absolute(config_path)
    if not cases or len(set(cases)) != len(cases) or any(case not in CASE_DIRECTORIES for case in cases):
        raise ValueError("invalid or duplicate acceptance cases")
    before = tomllib.loads(config_path.read_text(encoding="utf-8"))
    expected = copy.deepcopy(before)
    root.mkdir(parents=True, exist_ok=True)
    manifest = root / "PREPARED_ACCEPTANCE.json"
    if manifest.exists():
        raise FileExistsError("acceptance preparation already exists")
    # Failed preparation is retained too: a retry requires a fresh root.
    with (root / ".PREPARING").open("x", encoding="utf-8"):
        pass
    selected = {}
    for case in cases:
        short_id = uuid4().hex[:12]
        fixture = root / CASE_DIRECTORIES[case] / short_id
        if fixture.resolve() != fixture:
            raise ValueError("acceptance fixture path is redirected")
        project = fixture / "project"
        key = os.path.normcase(str(project))
        if key in expected.get("projects", {}):
            raise ValueError("prepared project already has a Codex configuration entry")
        fixture.mkdir(parents=True, exist_ok=False)
        project.mkdir()
        initialize_project(project)
        expected.setdefault("projects", {})[key] = {"trust_level": "trusted"}
        config_bytes = config_path.read_bytes()
        current = tomllib.loads(config_bytes.decode("utf-8"))
        if not _same_toml(current, expected):
            raise RuntimeError("initialization must change only the selected project trust")
        selected[case] = {"short_id": short_id, "root": str(fixture), "project": str(project)}
    frozen = {"path": str(config_path), "size": len(config_bytes),
              "sha256": hashlib.sha256(config_bytes).hexdigest()}
    if _descriptor(config_path) != frozen:
        raise RuntimeError("Codex config changed while freezing acceptance preparation")
    payload = {"schema": SCHEMA, "root": str(root), "cases": selected,
               "config_descriptor": frozen}
    with manifest.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return manifest


def resolve_acceptance_fixture(
    case: str, *, environment: Mapping[str, str] | None = None,
) -> Path:
    """Claim a bound prepared fixture, or allocate a fresh standalone fixture."""
    if case not in CASE_DIRECTORIES:
        raise ValueError("unknown acceptance case")
    environment = os.environ if environment is None else environment
    manifest_value = environment.get("AEGIS_APP_SERVER_PREPARED_MANIFEST")
    digest = environment.get("AEGIS_APP_SERVER_PREPARED_SHA256")
    configured_root = environment.get("AEGIS_APP_SERVER_ACCEPTANCE_ROOT")
    if (manifest_value is not None or digest is not None) and not configured_root:
        raise ValueError("prepared acceptance requires an explicit acceptance root")
    root = _absolute(
        configured_root if configured_root is not None
        else Path(tempfile.gettempdir()) / "aegis-acceptance"
    )
    if manifest_value is None and digest is None:
        fixture = root / CASE_DIRECTORIES[case] / uuid4().hex[:12]
        fixture.mkdir(parents=True, exist_ok=False)
        return fixture
    if not manifest_value or not digest or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        raise ValueError("prepared acceptance requires manifest and SHA-256")
    manifest = _absolute(manifest_value)
    if manifest != root / "PREPARED_ACCEPTANCE.json":
        raise ValueError("prepared manifest belongs to another acceptance root")
    content = manifest.read_bytes()
    if hashlib.sha256(content).hexdigest() != digest:
        raise ValueError("prepared manifest SHA-256 mismatch")
    payload = json.loads(content)
    if not isinstance(payload, dict) or payload.get("schema") != SCHEMA or payload.get("root") != str(root):
        raise ValueError("invalid prepared acceptance header")
    selected = payload.get("cases")
    if not isinstance(selected, dict) or not selected or set(selected) - CASE_DIRECTORIES.keys():
        raise ValueError("invalid prepared acceptance cases")
    if case not in selected:
        raise ValueError("case absent from prepared acceptance")
    for selected_case, entry in selected.items():
        if not isinstance(entry, dict) or not isinstance(entry.get("short_id"), str) or re.fullmatch(r"[0-9a-f]{12}", entry["short_id"]) is None:
            raise ValueError("invalid prepared fixture identity")
        expected_root = root / CASE_DIRECTORIES[selected_case] / entry["short_id"]
        project = expected_root / "project"
        if entry.get("root") != str(expected_root) or entry.get("project") != str(project):
            raise ValueError("prepared fixture path mismatch")
        if expected_root.resolve() != expected_root or project.resolve() != project or not project.is_dir():
            raise ValueError("prepared fixture missing or redirected")
    bound_config = payload.get("config_descriptor")
    if not isinstance(bound_config, dict) or not isinstance(bound_config.get("path"), str):
        raise ValueError("prepared config descriptor missing")
    if _descriptor(_absolute(bound_config["path"])) != bound_config:
        raise RuntimeError("Codex config changed after acceptance preparation")
    fixture = Path(selected[case]["root"])
    with (fixture / "CLAIMED").open("x", encoding="utf-8") as stream:
        stream.write(digest + "\n")
    return fixture
