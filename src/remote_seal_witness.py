from __future__ import annotations

import base64
import json
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

from path_security import PathSecurityError, read_regular_file
from project_seal_store import (
    ProjectSealStoreError,
    StoredProjectSeal,
    hold_verified_project_git_runtime,
)
from runtime_identity import RuntimeIdentityError, trusted_git_environment


WITNESS_CONFIG_RELATIVE_PATH = Path("config/seal_witness.json")
WITNESS_CONFIG_SCHEMA = "aegis.remote_seal_witness_config.v3"
WITNESS_SCHEMA = "aegis.remote_seal_witness.v3"
WITNESS_FILE_NAME = "aegis-seal-witness.json"
SSH_KNOWN_HOSTS_RELATIVE_PATH = Path("config/git_ssh_known_hosts")

_CONFIG_FIELDS = {"schema", "repository_url", "protected_ref", "ssh_identity"}
_SSH_IDENTITY_FIELDS = {"path", "sha256"}
_WITNESS_FIELDS = {
    "schema",
    "project_id_hex",
    "seal_chain_id_hex",
    "sequence",
    "expected_seal",
    "scope_policy_sha256",
    "scope_decision_sha256",
    "resolved_manifest_sha256",
    "git_commit",
    "runtime_authority_id",
}
_REF_PATTERN = re.compile(r"refs/heads/[A-Za-z0-9][A-Za-z0-9._/-]{0,240}")
_HEX_16_PATTERN = re.compile(r"[0-9a-f]{32}")
_HEX_32_PATTERN = re.compile(r"[0-9a-f]{64}")
_GIT_HEAD_PATTERN = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")
_SEAL_PATTERN = re.compile(r"ASC1:[0-9a-f]{64}")


class RemoteSealWitnessError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class VerifiedRemoteSealWitness:
    repository_url: str
    protected_ref: str
    git_commit: str
    sequence: int
    expected_seal: str
    runtime_authority_id: str


Runner = Callable[..., subprocess.CompletedProcess[str]]


def assert_remote_witness_not_published(
    project_root: str | Path,
    *,
    runner: Runner = subprocess.run,
    git_executable: str | None = None,
    git_runtime_lock_held: bool = False,
) -> None:
    """Permit authority initialization only before the protected ref exists."""
    project = Path(project_root).resolve()
    if not git_runtime_lock_held:
        try:
            with hold_verified_project_git_runtime(
                project, git_executable=git_executable
            ) as locked_git:
                return assert_remote_witness_not_published(
                    project,
                    runner=runner,
                    git_executable=locked_git,
                    git_runtime_lock_held=True,
                )
        except ProjectSealStoreError as error:
            raise RemoteSealWitnessError(str(error)) from error
    repository_url, protected_ref, identity_file, identity_sha256 = (
        _load_witness_config(project)
    )
    _validate_known_hosts(project, repository_url)
    git = git_executable or shutil.which("git")
    if not git:
        raise RemoteSealWitnessError("git executable is unavailable")
    try:
        environment = trusted_git_environment(
            git,
            ssh_known_hosts=project / SSH_KNOWN_HOSTS_RELATIVE_PATH,
            ssh_identity_file=identity_file,
            expected_ssh_identity_sha256=identity_sha256,
        )
        with tempfile.TemporaryDirectory(prefix="aegis-witness-proof-") as directory:
            command = [
                git,
                "--no-pager",
                "ls-remote",
                "--exit-code",
                repository_url,
                protected_ref,
            ]
            completed = runner(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="strict",
                check=False,
                timeout=120,
                cwd=directory,
                env=environment,
            )
    except (RuntimeIdentityError, OSError, subprocess.TimeoutExpired, UnicodeError) as error:
        raise RemoteSealWitnessError(
            f"cannot prove remote witness ref absence: {error}"
        ) from error
    if completed.returncode == 2 and not completed.stdout.strip():
        return
    if completed.returncode == 0 and completed.stdout.strip():
        raise RemoteSealWitnessError(
            "runtime authority is already witnessed remotely and cannot be reinitialized"
        )
    raise RemoteSealWitnessError(
        "cannot prove remote witness ref absence; authority initialization fails closed: "
        f"exit_code={completed.returncode}, stderr={completed.stderr!r}"
    )


def verify_remote_project_seal_witness(
    project_root: str | Path,
    seal: StoredProjectSeal,
    *,
    runner: Runner = subprocess.run,
    git_executable: str | None = None,
    git_runtime_lock_held: bool = False,
) -> VerifiedRemoteSealWitness:
    project = Path(project_root).resolve()
    if not git_runtime_lock_held:
        try:
            with hold_verified_project_git_runtime(
                project, git_executable=git_executable
            ) as locked_git:
                return verify_remote_project_seal_witness(
                    project,
                    seal,
                    runner=runner,
                    git_executable=locked_git,
                    git_runtime_lock_held=True,
                )
        except ProjectSealStoreError as error:
            raise RemoteSealWitnessError(str(error)) from error
    repository_url, protected_ref, identity_file, identity_sha256 = (
        _load_witness_config(project)
    )
    _validate_known_hosts(project, repository_url)
    git = git_executable or shutil.which("git")
    if not git:
        raise RemoteSealWitnessError("git executable is unavailable")
    try:
        environment = trusted_git_environment(
            git,
            ssh_known_hosts=project / SSH_KNOWN_HOSTS_RELATIVE_PATH,
            ssh_identity_file=identity_file,
            expected_ssh_identity_sha256=identity_sha256,
        )
    except RuntimeIdentityError as error:
        raise RemoteSealWitnessError(str(error)) from error
    with tempfile.TemporaryDirectory(prefix="aegis-witness-fetch-") as directory:
        temporary_root = Path(directory)
        bare_repository = temporary_root / "witness.git"
        empty_template = temporary_root / "empty-template"
        empty_template.mkdir()
        _run_git(
            runner,
            [
                git,
                "--no-pager",
                "init",
                "--bare",
                f"--template={empty_template}",
                "--initial-branch=aegis-witness-temp",
                str(bare_repository),
            ],
            "initialize isolated witness repository",
            environment=environment,
            working_directory=temporary_root,
        )
        cache_ref = f"refs/aegis/witness-cache/{seal.project_id.hex()}"
        trusted_prefix = [
            git,
            "--no-pager",
            f"--git-dir={bare_repository}",
            "-c",
            "core.hooksPath=NUL",
            "-c",
            "protocol.file.allow=never",
        ]
        _run_git(
            runner,
            [
                *trusted_prefix,
                "fetch",
                "--no-tags",
                "--force",
                repository_url,
                f"{protected_ref}:{cache_ref}",
            ],
            "fetch protected remote seal witness",
            environment=environment,
            working_directory=temporary_root,
        )
        witness_text = _run_git(
            runner,
            [
                *trusted_prefix,
                "cat-file",
                "blob",
                f"{cache_ref}:{WITNESS_FILE_NAME}",
            ],
            "read protected remote seal witness",
            environment=environment,
            working_directory=temporary_root,
        )
    try:
        witness = json.loads(witness_text)
    except json.JSONDecodeError as error:
        raise RemoteSealWitnessError(
            f"remote seal witness JSON is invalid: {error}"
        ) from error
    parsed = _parse_witness(witness)
    if parsed["git_commit"] != seal.git_head_before_record:
        raise RemoteSealWitnessError(
            "remote seal witness does not match the commit bound to the local seal"
        )
    expected = {
        "project_id_hex": seal.project_id.hex(),
        "seal_chain_id_hex": seal.seal_chain_id.hex(),
        "sequence": seal.sequence,
        "expected_seal": seal.expected_seal,
        "scope_policy_sha256": seal.scope_policy_sha256,
        "scope_decision_sha256": seal.scope_decision_sha256,
        "resolved_manifest_sha256": seal.resolved_manifest_sha256,
        "runtime_authority_id": seal.runtime_authority_id,
    }
    for field, expected_value in expected.items():
        if parsed[field] != expected_value:
            raise RemoteSealWitnessError(
                f"remote seal witness does not match local {field}"
            )
    return VerifiedRemoteSealWitness(
        repository_url=repository_url,
        protected_ref=protected_ref,
        git_commit=seal.git_head_before_record,
        sequence=seal.sequence,
        expected_seal=seal.expected_seal,
        runtime_authority_id=seal.runtime_authority_id,
    )


def _parse_witness(value: Any) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != _WITNESS_FIELDS:
        raise RemoteSealWitnessError("remote seal witness has invalid fields")
    if value["schema"] != WITNESS_SCHEMA:
        raise RemoteSealWitnessError("remote seal witness has an unsupported schema")
    patterns = {
        "project_id_hex": _HEX_16_PATTERN,
        "seal_chain_id_hex": _HEX_16_PATTERN,
        "expected_seal": _SEAL_PATTERN,
        "scope_policy_sha256": _HEX_32_PATTERN,
        "scope_decision_sha256": _HEX_32_PATTERN,
        "resolved_manifest_sha256": _HEX_32_PATTERN,
        "git_commit": _GIT_HEAD_PATTERN,
        "runtime_authority_id": _HEX_16_PATTERN,
    }
    for field, pattern in patterns.items():
        item = value[field]
        if not isinstance(item, str) or pattern.fullmatch(item) is None:
            raise RemoteSealWitnessError(
                f"remote seal witness has an invalid {field}"
            )
    sequence = value["sequence"]
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
        raise RemoteSealWitnessError("remote seal witness has an invalid sequence")
    return value


def _load_json(path: Path, *, allowed_root: Path, description: str) -> Any:
    try:
        encoded, _identity = read_regular_file(
            path,
            allowed_root=allowed_root,
            label=description,
            max_bytes=1024 * 1024,
        )
        return json.loads(encoded.decode("utf-8", errors="strict"))
    except PathSecurityError as error:
        raise RemoteSealWitnessError(str(error)) from error
    except (UnicodeError, json.JSONDecodeError) as error:
        raise RemoteSealWitnessError(
            f"{description} cannot be read: {path}: {error}"
        ) from error


def _load_witness_config(project: Path) -> tuple[str, str, Path, str]:
    config = _load_json(
        project / WITNESS_CONFIG_RELATIVE_PATH,
        allowed_root=project,
        description="remote seal witness config",
    )
    if not isinstance(config, dict) or set(config) != _CONFIG_FIELDS:
        raise RemoteSealWitnessError("remote seal witness config has invalid fields")
    if config["schema"] != WITNESS_CONFIG_SCHEMA:
        raise RemoteSealWitnessError(
            "remote seal witness config has an unsupported schema"
        )
    repository_url = config["repository_url"]
    if not isinstance(repository_url, str) or not _canonical_ssh_url(repository_url):
        raise RemoteSealWitnessError(
            "remote seal witness has an invalid canonical repository URL"
        )
    protected_ref = config["protected_ref"]
    if (
        not isinstance(protected_ref, str)
        or _REF_PATTERN.fullmatch(protected_ref) is None
        or ".." in protected_ref
        or protected_ref.endswith("/")
    ):
        raise RemoteSealWitnessError(
            "remote seal witness has an invalid protected ref"
        )
    identity = config["ssh_identity"]
    if not isinstance(identity, dict) or set(identity) != _SSH_IDENTITY_FIELDS:
        raise RemoteSealWitnessError(
            "remote seal witness SSH identity descriptor is invalid"
        )
    identity_path_value = identity["path"]
    identity_sha256 = identity["sha256"]
    if (
        not isinstance(identity_path_value, str)
        or not identity_path_value.isascii()
        or "\x00" in identity_path_value
        or not Path(identity_path_value).is_absolute()
        or not isinstance(identity_sha256, str)
        or _HEX_32_PATTERN.fullmatch(identity_sha256) is None
    ):
        raise RemoteSealWitnessError(
            "remote seal witness SSH identity descriptor is invalid"
        )
    return repository_url, protected_ref, Path(identity_path_value), identity_sha256


def _canonical_ssh_url(value: str) -> bool:
    if not value.isascii() or any(character.isspace() for character in value):
        return False
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return False
    if (
        parsed.scheme != "ssh"
        or not parsed.username
        or re.fullmatch(r"[A-Za-z0-9._-]+", parsed.username) is None
        or parsed.password is not None
        or not parsed.hostname
        or parsed.hostname != parsed.hostname.lower()
        or re.fullmatch(
            r"[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?", parsed.hostname
        )
        is None
        or port not in {None, 22}
        or parsed.query
        or parsed.fragment
        or not parsed.path.startswith("/")
        or not parsed.path.endswith(".git")
    ):
        return False
    parts = parsed.path.split("/")[1:]
    return bool(parts) and all(
        part not in {"", ".", ".."}
        and re.fullmatch(r"[A-Za-z0-9._-]+", part) is not None
        for part in parts
    )


def _validate_known_hosts(project: Path, repository_url: str) -> None:
    host = urlsplit(repository_url).hostname
    assert host is not None
    path = project / SSH_KNOWN_HOSTS_RELATIVE_PATH
    try:
        content, _identity = read_regular_file(
            path,
            allowed_root=project,
            label="sealed SSH known-hosts file",
            max_bytes=1024 * 1024,
        )
        text = content.decode("ascii", errors="strict")
    except (PathSecurityError, UnicodeError) as error:
        raise RemoteSealWitnessError(str(error)) from error
    expected_host = host if urlsplit(repository_url).port in {None, 22} else None
    entries = [line.split() for line in text.splitlines() if line.strip()]
    if len(entries) != 1 or len(entries[0]) != 3:
        raise RemoteSealWitnessError(
            "sealed SSH known-hosts file must contain exactly one host key"
        )
    entry_host, algorithm, encoded_key = entries[0]
    try:
        key = base64.b64decode(encoded_key, validate=True)
    except ValueError as error:
        raise RemoteSealWitnessError("sealed SSH host key is invalid") from error
    if (
        entry_host != expected_host
        or algorithm != "ssh-ed25519"
        or not key.startswith(b"\x00\x00\x00\x0bssh-ed25519")
    ):
        raise RemoteSealWitnessError(
            "sealed SSH host key does not match the canonical repository host"
        )


def _run_git(
    runner: Runner,
    command: list[str],
    description: str,
    *,
    environment: dict[str, str],
    working_directory: Path,
) -> str:
    try:
        completed = runner(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
            cwd=working_directory,
            env=environment,
            check=False,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired, UnicodeError) as error:
        raise RemoteSealWitnessError(f"{description} failed: {error}") from error
    if completed.returncode != 0:
        raise RemoteSealWitnessError(
            f"{description} failed: exit_code={completed.returncode}, "
            f"stderr={completed.stderr!r}"
        )
    return completed.stdout
