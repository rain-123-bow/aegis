from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import json
import os
import re
import shutil
import shlex
import sys
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
    git = lexical_absolute(git_command)
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


def capture_production_runtime_identity(
    project_root: str | Path,
    *,
    codex_command: str | Path,
    tracerelay_command: str | Path,
    git_command: str | Path,
) -> dict[str, Any]:
    project = Path(project_root).resolve()
    files: dict[str, dict[str, object]] = {}
    watched_roots: dict[str, str] = {}

    def add(path: str | Path, source: str) -> None:
        candidate = lexical_absolute(path)
        key = str(candidate).casefold()
        if key in files:
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
        files[key] = {
            "path": str(candidate),
            "source": source,
            "size": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
            "file_identity": {
                "device": identity.device,
                "inode": identity.inode,
                "size": identity.size,
                "modified_ns": identity.modified_ns,
                "changed_ns": identity.changed_ns,
            },
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

    installed_versions = sorted(
        {
            (
                str(distribution.metadata.get("Name") or distribution.name),
                str(distribution.version),
            )
            for distribution in importlib.metadata.distributions()
        },
        key=lambda item: item[0].casefold(),
    )

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

    tracerelay = lexical_absolute(tracerelay_command)
    add(tracerelay, "tracerelay_launcher")
    _verify_tracerelay_source_identity(project, add)

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


def _verify_tracerelay_source_identity(project: Path, add: Any) -> None:
    sealed_source = project / "submodules" / "TraceRelay" / "src" / "tracerelay"
    try:
        package = importlib.import_module("tracerelay")
    except (ImportError, AttributeError) as error:
        raise RuntimeIdentityError("TraceRelay Python package is unavailable") from error
    package_file = getattr(package, "__file__", None)
    if not isinstance(package_file, str):
        raise RuntimeIdentityError("TraceRelay package has no filesystem identity")
    installed_source = Path(package_file).resolve().parent
    for source_path in sealed_source.rglob("*.py"):
        relative = source_path.relative_to(sealed_source)
        installed_path = installed_source / relative
        if not installed_path.is_file():
            raise RuntimeIdentityError(
                f"installed TraceRelay omits sealed source file: {relative.as_posix()}"
            )
        sealed = source_path.read_bytes()
        installed = installed_path.read_bytes()
        if sealed != installed:
            raise RuntimeIdentityError(
                f"installed TraceRelay differs from sealed source: {relative.as_posix()}"
            )
        add(installed_path, "tracerelay_installed_source")
