from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import re
import shutil
import shlex
import sys
from collections.abc import Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

from path_security import (
    PathSecurityError,
    StablePathSpec,
    hold_paths_stable,
    lexical_absolute,
    read_regular_file,
)


class RuntimeIdentityError(RuntimeError):
    pass


_GIT_RUNTIME_ROOTS = (
    Path("mingw64/bin"),
    Path("mingw64/libexec/git-core"),
    Path("usr/bin"),
)
_TRACERELAY_COMPONENT_ROOT = Path("third_party/TraceRelay")
_TRACERELAY_SNAPSHOT_ROOT = Path("src/tracerelay")
_TRACERELAY_SDK_SOURCE = _TRACERELAY_COMPONENT_ROOT / _TRACERELAY_SNAPSHOT_ROOT
_TRACERELAY_SDK_PROVENANCE = Path("third_party/TraceRelay/PROVENANCE.json")
_TRACERELAY_PROVENANCE_SCHEMA = "aegis.third_party_python_sdk_snapshot.v1"
_TRACERELAY_SOURCE_REPOSITORY = "git@github.com:rain-123-bow/TraceRelay.git"


def git_runtime_manifest(
    git_command: str | Path,
) -> tuple[list[Path], str]:
    git = lexical_absolute(git_command)
    git_root = git.parent.parent
    ordered = _git_runtime_files(git)
    entries: list[dict[str, object]] = []
    for path in ordered:
        try:
            content, _identity = read_regular_file(
                path,
                allowed_root=git_root,
                label="Git runtime dependency",
                max_bytes=1024 * 1024 * 1024,
            )
        except PathSecurityError as error:
            raise RuntimeIdentityError(str(error)) from error
        entries.append(
            {
                "path": path.relative_to(git_root).as_posix(),
                "size": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )
    encoded = json.dumps(
        entries,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return ordered, hashlib.sha256(encoded).hexdigest()


def _git_runtime_files(git_command: str | Path) -> list[Path]:
    git = lexical_absolute(git_command).resolve(strict=True)
    git_root = git.parent.parent
    candidates: dict[str, Path] = {str(git).casefold(): git}
    for relative in _GIT_RUNTIME_ROOTS:
        root = git_root / relative
        if root.is_dir():
            for path in root.rglob("*"):
                if path.is_file():
                    candidate = lexical_absolute(path)
                    candidates.setdefault(str(candidate).casefold(), candidate)
    return sorted(candidates.values(), key=lambda path: str(path).casefold())


@contextmanager
def hold_verified_git_runtime(
    git_command: str | Path,
    *,
    expected_launcher_sha256: str,
    expected_runtime_sha256: str,
) -> Iterator[str]:
    """Keep the complete pinned Git runtime immutable through every Git call."""
    git = lexical_absolute(git_command)
    git_root = git.parent.parent
    files = _git_runtime_files(git)
    specs = [
        StablePathSpec(
            path=path,
            allowed_root=git_root,
            label="pinned Git runtime file",
        )
        for path in files
    ]
    for relative in _GIT_RUNTIME_ROOTS:
        root = git_root / relative
        if root.is_dir():
            specs.append(
                StablePathSpec(
                    path=root,
                    allowed_root=git_root,
                    label="pinned Git runtime root",
                    directory=True,
                )
            )
    try:
        with hold_paths_stable(specs):
            launcher, _identity = read_regular_file(
                git,
                allowed_root=git_root,
                label="locked Git launcher",
                max_bytes=512 * 1024 * 1024,
            )
            if hashlib.sha256(launcher).hexdigest() != expected_launcher_sha256:
                raise RuntimeIdentityError(
                    "Git executable differs from the user-confirmed runtime trust pin"
                )
            locked_files, locked_digest = git_runtime_manifest(git)
            if (
                [str(path).casefold() for path in locked_files]
                != [str(path).casefold() for path in files]
                or locked_digest != expected_runtime_sha256
            ):
                raise RuntimeIdentityError(
                    "Git runtime closure differs from the user-confirmed trust pin"
                )
            yield str(git)
    except PathSecurityError as error:
        raise RuntimeIdentityError(str(error)) from error


def trusted_git_environment(
    git_command: str | Path,
    *,
    ssh_known_hosts: str | Path | None = None,
    ssh_identity_file: str | Path | None = None,
    expected_ssh_identity_sha256: str | None = None,
) -> dict[str, str]:
    """Build the complete, non-inherited environment for trusted Git calls."""
    git = lexical_absolute(git_command)
    git_root = git.parent.parent
    system_root = _system_windows_directory()
    isolated_home = git_root
    path_entries = [
        git.parent,
        git_root / "mingw64" / "bin",
        git_root / "mingw64" / "libexec" / "git-core",
        git_root / "usr" / "bin",
        system_root / "System32",
    ]
    environment = {
        "GIT_ATTR_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_EXEC_PATH": str(git_root / "mingw64" / "libexec" / "git-core"),
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_PAGER": "",
        "GIT_TERMINAL_PROMPT": "0",
        "HOME": str(isolated_home),
        "LC_ALL": "C",
        "PAGER": "",
        "PATH": os.pathsep.join(str(path) for path in path_entries),
        "SSH_ASKPASS_REQUIRE": "never",
        "SystemRoot": str(system_root),
        "USERPROFILE": str(isolated_home),
        "WINDIR": str(system_root),
    }
    if ssh_known_hosts is None:
        if ssh_identity_file is not None or expected_ssh_identity_sha256 is not None:
            raise RuntimeIdentityError(
                "SSH identity inputs require a sealed SSH known-hosts file"
            )
        return environment
    if ssh_identity_file is None or expected_ssh_identity_sha256 is None:
        raise RuntimeIdentityError(
            "SSH transport requires an explicit identity file and SHA-256"
        )

    known_hosts = lexical_absolute(ssh_known_hosts)
    identity_file = lexical_absolute(ssh_identity_file)
    ssh = git_root / "usr" / "bin" / "ssh.exe"
    try:
        read_regular_file(
            ssh,
            allowed_root=git_root,
            label="pinned Git SSH executable",
            max_bytes=512 * 1024 * 1024,
        )
        read_regular_file(
            known_hosts,
            allowed_root=known_hosts.parent,
            label="sealed SSH known-hosts file",
            max_bytes=1024 * 1024,
        )
        identity_bytes, _identity = read_regular_file(
            identity_file,
            allowed_root=Path(identity_file.anchor),
            label="sealed SSH identity file",
            max_bytes=1024 * 1024,
        )
    except PathSecurityError as error:
        raise RuntimeIdentityError(str(error)) from error
    if hashlib.sha256(identity_bytes).hexdigest() != expected_ssh_identity_sha256:
        raise RuntimeIdentityError(
            "SSH identity file differs from the sealed transport descriptor"
        )
    isolated_home = known_hosts.parent
    environment["HOME"] = str(isolated_home)
    environment["USERPROFILE"] = str(isolated_home)
    known_hosts_argument = str(known_hosts).replace("\\", "/")
    identity_argument = str(identity_file).replace("\\", "/")
    ssh_arguments = [
        str(ssh).replace("\\", "/"),
        "-F",
        "/dev/null",
        "-o",
        "BatchMode=yes",
        "-o",
        "NumberOfPasswordPrompts=0",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        f"UserKnownHostsFile={known_hosts_argument}",
        "-o",
        "GlobalKnownHostsFile=/dev/null",
        "-o",
        "ProxyCommand=none",
        "-o",
        "ProxyJump=none",
        "-o",
        "HostKeyAlgorithms=ssh-ed25519",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "IdentityAgent=none",
        "-o",
        "PKCS11Provider=none",
        "-o",
        "SecurityKeyProvider=none",
        "-o",
        "IdentityFile=none",
        "-i",
        identity_argument,
    ]
    environment["GIT_SSH_COMMAND"] = shlex.join(ssh_arguments)
    environment["GIT_SSH_VARIANT"] = "ssh"
    return environment


def _system_windows_directory() -> Path:
    if os.name != "nt":
        return lexical_absolute("/")
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    get_windows_directory = kernel32.GetWindowsDirectoryW
    get_windows_directory.argtypes = [wintypes.LPWSTR, wintypes.UINT]
    get_windows_directory.restype = wintypes.UINT
    buffer = ctypes.create_unicode_buffer(32768)
    written = get_windows_directory(buffer, len(buffer))
    if written == 0 or written >= len(buffer):
        raise RuntimeIdentityError(
            f"cannot resolve the Windows directory: error={ctypes.get_last_error()}"
        )
    return lexical_absolute(buffer.value)


def _installed_distribution_versions() -> list[list[str]]:
    versions = {
        (
            str(distribution.metadata.get("Name") or distribution.name),
            str(distribution.version),
        )
        for distribution in importlib.metadata.distributions()
    }
    return [
        [name, version]
        for name, version in sorted(
            versions,
            key=lambda item: (item[0].casefold(), item[0], item[1]),
        )
    ]


def _stable_file_identity(identity: Any) -> dict[str, int]:
    """Return identity fields that remain stable while Windows executes a file.

    NTFS ChangeTime can advance when installed Git and Codex executables run even
    though their file object, content, size, and modification time are unchanged.
    Content authority remains bound by the independently verified SHA-256.
    """

    return {
        "device": int(identity.device),
        "inode": int(identity.inode),
        "size": int(identity.size),
        "modified_ns": int(identity.modified_ns),
    }


def capture_production_runtime_identity(
    project_root: str | Path,
    *,
    codex_command: str | Path,
    tracerelay_command: str | Path | Sequence[str],
    git_command: str | Path,
) -> dict[str, Any]:
    project = Path(project_root).resolve()
    files: dict[str, dict[str, object]] = {}
    watched_roots: dict[str, str] = {}

    def add(
        path: str | Path,
        source: str,
        expected_size: int | None = None,
        expected_sha256: str | None = None,
    ) -> None:
        candidate = lexical_absolute(path)
        key = str(candidate).casefold()
        if key in files:
            existing = files[key]
            if (
                expected_size is not None
                and existing["size"] != expected_size
            ) or (
                expected_sha256 is not None
                and existing["sha256"] != expected_sha256
            ):
                raise RuntimeIdentityError(
                    f"production runtime dependency differs: {candidate}"
                )
            return
        try:
            content, identity = read_regular_file(
                candidate,
                allowed_root=Path(candidate.anchor),
                label=f"production runtime dependency {source}",
                max_bytes=1024 * 1024 * 1024,
            )
        except PathSecurityError as error:
            raise RuntimeIdentityError(str(error)) from error
        sha256 = hashlib.sha256(content).hexdigest()
        if (
            expected_size is not None
            and len(content) != expected_size
        ) or (
            expected_sha256 is not None
            and sha256 != expected_sha256
        ):
            raise RuntimeIdentityError(
                f"production runtime dependency differs: {candidate}"
            )
        files[key] = {
            "path": str(candidate),
            "source": source,
            "size": len(content),
            "sha256": sha256,
            "file_identity": _stable_file_identity(identity),
        }

    add(sys.executable, "python_executable")
    add(sys._base_executable, "python_base_executable")
    if not sys.flags.isolated:
        raise RuntimeIdentityError(
            "production Aegis must run under Python isolated mode (-I)"
        )
    if not sys.dont_write_bytecode or sys.pycache_prefix is None:
        raise RuntimeIdentityError(
            "production Aegis must use -B and an explicit empty pycache prefix"
        )
    pycache_root = lexical_absolute(sys.pycache_prefix)
    if not pycache_root.is_dir() or any(pycache_root.iterdir()):
        raise RuntimeIdentityError(
            "production pycache prefix must be an existing empty directory"
        )
    watched_roots[str(pycache_root).casefold()] = str(pycache_root)

    python_roots: dict[str, Path] = {}
    for value in (
        *sys.path,
        str(Path(sys.base_prefix) / "Lib"),
        str(Path(sys.base_prefix) / "DLLs"),
        str(Path(sys.prefix) / "Lib" / "site-packages"),
    ):
        if not value:
            continue
        root = lexical_absolute(value)
        if root.is_dir():
            python_roots.setdefault(str(root).casefold(), root)
    for root in python_roots.values():
        watched_roots[str(root).casefold()] = str(root)
        for path in root.rglob("*"):
            if path.is_file():
                add(path, "python_import_root")
    for path in Path(sys.base_prefix).glob("*"):
        if path.is_file() and path.suffix.casefold() in {".dll", ".exe", ".pyd", ".zip"}:
            add(path, "python_native_runtime")
    for module in tuple(sys.modules.values()):
        module_file = getattr(module, "__file__", None)
        if isinstance(module_file, str) and Path(module_file).is_file():
            add(module_file, "python_loaded_module")

    requirements = _pinned_runtime_requirements(project / "requirements-runtime.txt")
    _validate_dependency_closure(requirements)
    distributions: list[dict[str, object]] = []
    for name, expected_version in requirements:
        try:
            distribution = importlib.metadata.distribution(name)
        except importlib.metadata.PackageNotFoundError as error:
            raise RuntimeIdentityError(
                f"pinned runtime distribution is not installed: {name}"
            ) from error
        if distribution.version != expected_version:
            raise RuntimeIdentityError(
                f"runtime distribution version differs from its pin: "
                f"{name} expected={expected_version} actual={distribution.version}"
            )
        distribution_paths: list[str] = []
        for relative in distribution.files or ():
            path = Path(distribution.locate_file(relative)).resolve()
            if not path.is_file():
                continue
            add(path, f"python_distribution:{name}")
            distribution_paths.append(str(path))
        distributions.append(
            {
                "name": name,
                "version": distribution.version,
                "files": sorted(distribution_paths, key=str.casefold),
            }
        )

    installed_versions = _installed_distribution_versions()

    codex = lexical_absolute(codex_command)
    add(codex, "codex_launcher")
    node = shutil.which("node.exe") or shutil.which("node")
    if node is None:
        raise RuntimeIdentityError("Node.js executable used by Codex is unavailable")
    add(node, "codex_node_runtime")
    npm_root = codex.parent / "node_modules" / "@openai"
    codex_packages = [
        path
        for path in npm_root.glob("codex*")
        if path.is_dir()
    ]
    if not codex_packages:
        raise RuntimeIdentityError("Codex package closure is unavailable beside its launcher")
    for package in codex_packages:
        watched_roots[str(package.resolve()).casefold()] = str(package.resolve())
        for path in package.rglob("*"):
            if path.is_file():
                add(path, "codex_package")

    tracerelay_prefix = _normalize_tracerelay_command(tracerelay_command)
    expected_tracerelay_prefix = (
        str(lexical_absolute(sys.executable)),
        "-I",
        "-B",
        "-m",
        "tracerelay",
    )
    if tracerelay_prefix != expected_tracerelay_prefix:
        raise RuntimeIdentityError(
            "TraceRelay must execute as an SDK in the active Aegis Python runtime"
        )
    tracerelay_sdk = _verify_tracerelay_source_identity(project, add)
    installed_tracerelay_root = str(tracerelay_sdk["installed_package_root"])
    watched_roots[installed_tracerelay_root.casefold()] = installed_tracerelay_root

    git = lexical_absolute(git_command)
    git_files, git_runtime_sha256 = git_runtime_manifest(git)
    for path in git_files:
        add(path, "git_runtime")
        watched_roots[str(path.parent).casefold()] = str(path.parent)

    environment = {
        name: hashlib.sha256(value.encode("utf-8")).hexdigest()
        for name, value in sorted(os.environ.items(), key=lambda item: item[0].casefold())
    }
    ordered_files = sorted(files.values(), key=lambda item: str(item["path"]).casefold())
    body = {
        "schema": "aegis.production_runtime_identity.v1",
        "python_version": sys.version.splitlines()[0],
        "python_isolated": bool(sys.flags.isolated),
        "python_dont_write_bytecode": bool(sys.dont_write_bytecode),
        "python_pycache_prefix": str(Path(sys.pycache_prefix).resolve()),
        "distributions": distributions,
        "installed_distribution_versions": installed_versions,
        "tracerelay_command": list(tracerelay_prefix),
        "tracerelay_sdk": tracerelay_sdk,
        "git_runtime_sha256": git_runtime_sha256,
        "environment_value_sha256": environment,
        "watched_roots": sorted(watched_roots.values(), key=str.casefold),
        "files": ordered_files,
    }
    body["manifest_sha256"] = hashlib.sha256(
        json.dumps(
            body,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return body


def _pinned_runtime_requirements(path: Path) -> list[tuple[str, str]]:
    try:
        content, _identity = read_regular_file(
            path,
            allowed_root=path.parent,
            label="runtime dependency lock",
            max_bytes=4 * 1024 * 1024,
        )
    except PathSecurityError as error:
        raise RuntimeIdentityError(str(error)) from error
    requirements: list[tuple[str, str]] = []
    for line in content.decode("utf-8", errors="strict").splitlines():
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)(?:\[[A-Za-z0-9_,.-]+\])?==([^\s;]+)", value)
        if match is None:
            raise RuntimeIdentityError(
                f"runtime dependency lock contains a non-exact requirement: {value}"
            )
        requirements.append((match.group(1), match.group(2)))
    if not requirements:
        raise RuntimeIdentityError("runtime dependency lock is empty")
    return requirements


def _validate_dependency_closure(requirements: list[tuple[str, str]]) -> None:
    locked = {canonicalize_name(name): version for name, version in requirements}
    for name, _version in requirements:
        distribution = importlib.metadata.distribution(name)
        for raw_requirement in distribution.requires or ():
            requirement = Requirement(raw_requirement)
            if requirement.marker is not None and not requirement.marker.evaluate():
                continue
            dependency = canonicalize_name(requirement.name)
            if dependency not in locked:
                raise RuntimeIdentityError(
                    f"runtime dependency closure is not fully locked: {name} requires {requirement.name}"
                )
            installed = importlib.metadata.version(requirement.name)
            if requirement.specifier and installed not in requirement.specifier:
                raise RuntimeIdentityError(
                    f"locked dependency does not satisfy runtime requirement: "
                    f"{name} requires {requirement}, installed={installed}"
                )


def _normalize_tracerelay_command(
    command: str | Path | Sequence[str],
) -> tuple[str, ...]:
    if isinstance(command, (str, Path)):
        return (str(lexical_absolute(command)),)
    prefix = tuple(str(part) for part in command)
    if not prefix:
        raise RuntimeIdentityError("TraceRelay command prefix is empty")
    return (str(lexical_absolute(prefix[0])), *prefix[1:])


def _verify_tracerelay_source_identity(
    project: Path, add: Any
) -> dict[str, str]:
    sealed_source = project / _TRACERELAY_SDK_SOURCE
    if not sealed_source.is_dir():
        raise RuntimeIdentityError(
            f"TraceRelay SDK source snapshot is unavailable: {sealed_source}"
        )
    provenance_path = project / _TRACERELAY_SDK_PROVENANCE
    provenance, provenance_content = _load_tracerelay_provenance(provenance_path)
    descriptors = provenance["files"]
    if not isinstance(descriptors, list):
        raise RuntimeIdentityError("TraceRelay provenance files must be a list")
    expected_paths: dict[str, tuple[int, str]] = {}
    normalized_descriptors: list[dict[str, object]] = []
    prefix = _TRACERELAY_SNAPSHOT_ROOT.as_posix() + "/"
    for descriptor in descriptors:
        if not isinstance(descriptor, dict) or set(descriptor) != {
            "path",
            "size",
            "sha256",
        }:
            raise RuntimeIdentityError(
                "TraceRelay provenance contains an invalid file descriptor"
            )
        path_value = descriptor["path"]
        size = descriptor["size"]
        sha256 = descriptor["sha256"]
        if (
            not isinstance(path_value, str)
            or not path_value.startswith(prefix)
            or Path(path_value).as_posix() != path_value
            or ".." in Path(path_value).parts
            or isinstance(size, bool)
            or not isinstance(size, int)
            or size < 0
            or not isinstance(sha256, str)
            or re.fullmatch(r"[0-9a-f]{64}", sha256) is None
        ):
            raise RuntimeIdentityError(
                "TraceRelay provenance contains a non-canonical file descriptor"
            )
        relative = path_value.removeprefix(prefix)
        if not relative or relative in expected_paths:
            raise RuntimeIdentityError(
                "TraceRelay provenance contains a duplicate or empty source path"
            )
        expected_paths[relative] = (size, sha256)
        normalized_descriptors.append(
            {"path": path_value, "size": size, "sha256": sha256}
        )
    ordered_paths = sorted(
        expected_paths,
        key=lambda value: value.encode("utf-8"),
    )
    if list(expected_paths) != ordered_paths:
        raise RuntimeIdentityError(
            "TraceRelay provenance file descriptors are not canonically ordered"
        )
    encoded_manifest = json.dumps(
        normalized_descriptors,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    if hashlib.sha256(encoded_manifest).hexdigest() != provenance[
        "snapshot_manifest_sha256"
    ]:
        raise RuntimeIdentityError("TraceRelay provenance manifest hash differs")
    actual_snapshot = _exact_tree_files(sealed_source, "TraceRelay SDK snapshot")
    if set(actual_snapshot) != set(expected_paths):
        raise RuntimeIdentityError(
            "TraceRelay SDK snapshot file set differs from its provenance"
        )
    add(
        provenance_path,
        "tracerelay_sdk_provenance",
        len(provenance_content),
        hashlib.sha256(provenance_content).hexdigest(),
    )
    for relative, path in actual_snapshot.items():
        expected_size, expected_sha256 = expected_paths[relative]
        add(
            path,
            "tracerelay_sdk_snapshot",
            expected_size,
            expected_sha256,
        )
    installed_source = _locate_installed_tracerelay_source()
    try:
        installed_source.relative_to(project)
    except ValueError:
        pass
    else:
        raise RuntimeIdentityError(
            "TraceRelay must be installed as an SDK outside the Aegis repository"
        )
    installed_paths = _exact_tree_files(
        installed_source, "installed TraceRelay SDK package"
    )
    if set(installed_paths) != set(expected_paths):
        raise RuntimeIdentityError(
            "installed TraceRelay SDK file set differs from the sealed snapshot"
        )
    for relative, installed_path in installed_paths.items():
        expected_size, expected_sha256 = expected_paths[relative]
        add(
            installed_path,
            "tracerelay_installed_source",
            expected_size,
            expected_sha256,
        )
    return {
        "source_repository": str(provenance["source_repository"]),
        "source_commit": str(provenance["source_commit"]),
        "snapshot_manifest_sha256": str(provenance["snapshot_manifest_sha256"]),
        "installed_package_root": str(installed_source),
    }


def _locate_installed_tracerelay_source() -> Path:
    distributions = []
    for distribution in importlib.metadata.distributions():
        name = distribution.metadata.get("Name")
        if isinstance(name, str) and canonicalize_name(name) == "tracerelay":
            distributions.append(distribution)
    if len(distributions) != 1:
        raise RuntimeIdentityError(
            "exactly one installed TraceRelay distribution is required"
        )
    distribution = distributions[0]
    candidates: list[Path] = []
    for relative in distribution.files or ():
        normalized = Path(relative)
        if normalized.as_posix() != "tracerelay/__init__.py":
            continue
        located = Path(distribution.locate_file(relative))
        if not located.is_file():
            raise RuntimeIdentityError(
                "installed TraceRelay distribution has no package initializer"
            )
        candidates.append(located.resolve().parent)
    if len(candidates) != 1:
        raise RuntimeIdentityError(
            "installed TraceRelay package root is missing or ambiguous"
        )
    return candidates[0]


def _load_tracerelay_provenance(
    path: Path,
) -> tuple[dict[str, object], bytes]:
    try:
        content = path.read_bytes()
        raw = content.decode("utf-8", errors="strict")
        provenance = json.loads(raw, object_pairs_hook=_reject_duplicate_json_keys)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        raise RuntimeIdentityError("TraceRelay provenance is invalid") from error
    required = {
        "schema",
        "component",
        "source_repository",
        "source_commit",
        "source_tree_state",
        "snapshot_kind",
        "snapshot_root",
        "snapshot_manifest_sha256",
        "files",
    }
    if not isinstance(provenance, dict) or set(provenance) != required:
        raise RuntimeIdentityError("TraceRelay provenance schema fields differ")
    if (
        provenance["schema"] != _TRACERELAY_PROVENANCE_SCHEMA
        or provenance["component"] != "TraceRelay"
        or provenance["source_repository"] != _TRACERELAY_SOURCE_REPOSITORY
        or not isinstance(provenance["source_commit"], str)
        or re.fullmatch(r"[0-9a-f]{40}", provenance["source_commit"]) is None
        or provenance["source_tree_state"] != "clean"
        or provenance["snapshot_kind"] != "runtime-python-source"
        or provenance["snapshot_root"] != _TRACERELAY_SNAPSHOT_ROOT.as_posix()
        or not isinstance(provenance["snapshot_manifest_sha256"], str)
        or re.fullmatch(
            r"[0-9a-f]{64}", provenance["snapshot_manifest_sha256"]
        )
        is None
    ):
        raise RuntimeIdentityError("TraceRelay provenance identity differs")
    return provenance, content


def _reject_duplicate_json_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _exact_tree_files(root: Path, label: str) -> dict[str, Path]:
    if _is_link_or_junction(root):
        raise RuntimeIdentityError(f"{label} root is a link or junction")
    files: dict[str, Path] = {}
    for path in sorted(
        root.rglob("*"),
        key=lambda candidate: candidate.relative_to(root).as_posix().encode("utf-8"),
    ):
        relative = path.relative_to(root).as_posix()
        if _is_link_or_junction(path):
            raise RuntimeIdentityError(f"{label} contains a link or junction: {relative}")
        if path.is_dir():
            continue
        if not path.is_file():
            raise RuntimeIdentityError(f"{label} contains a non-file: {relative}")
        files[relative] = path
    if not files:
        raise RuntimeIdentityError(f"{label} is empty")
    return files


def _is_link_or_junction(path: Path) -> bool:
    is_junction = getattr(path, "is_junction", None)
    return path.is_symlink() or (callable(is_junction) and is_junction())
