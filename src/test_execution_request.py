from __future__ import annotations

import hashlib
import json
import re
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from path_security import (
    PathSecurityError,
    StablePathSpec,
    hold_paths_stable,
    is_within,
    lexical_absolute,
    read_regular_file,
    require_no_reparse,
    same_path,
)


TEST_EXECUTION_REQUEST_SCHEMA = "aegis.test_execution_request.v3"
TEST_EXECUTION_REQUEST_NAME = "TEST_EXECUTION_REQUEST.json"
TEST_EXECUTION_POLICY_SCHEMA = "aegis.test_execution_policy.v2"
TEST_EXECUTION_POLICY_BEGIN = "<!-- AEGIS_TEST_EXECUTION_POLICY_BEGIN -->"
TEST_EXECUTION_POLICY_END = "<!-- AEGIS_TEST_EXECUTION_POLICY_END -->"
_HEX_16 = re.compile(r"[0-9a-f]{32}")
_HEX_32 = re.compile(r"[0-9a-f]{64}")
_TOP_FIELDS = {
    "schema",
    "project_id_hex",
    "workflow_run_id",
    "attempt_id",
    "approved_test_plan_sha256",
    "tests",
}
_TEST_FIELDS = {
    "test_id",
    "requirement_ids",
    "command",
    "cwd",
    "environment",
    "timeout_seconds",
    "test_inputs",
    "executable",
}
_DESCRIPTOR_FIELDS = {"path", "size", "sha256"}
_POLICY_FIELDS = {"schema", "tests"}
_SHELL_EXECUTABLES = {
    "bash",
    "bash.exe",
    "cmd",
    "cmd.exe",
    "cscript.exe",
    "mshta.exe",
    "powershell.exe",
    "pwsh.exe",
    "rundll32.exe",
    "sh",
    "sh.exe",
    "wscript.exe",
    "wsl.exe",
}
_INLINE_FLAGS = {
    "node": {"-e", "--eval", "-p", "--print"},
    "node.exe": {"-e", "--eval", "-p", "--print"},
    "perl": {"-e"},
    "perl.exe": {"-e"},
    "python": {"-c", "-m"},
    "python.exe": {"-c", "-m"},
    "python3": {"-c", "-m"},
    "python3.exe": {"-c", "-m"},
    "ruby": {"-e"},
    "ruby.exe": {"-e"},
}
_EXECUTABLE_INPUT_SUFFIXES = {
    ".bat",
    ".cmd",
    ".dll",
    ".exe",
    ".jar",
    ".js",
    ".mjs",
    ".ps1",
    ".py",
    ".pyw",
}
class TestExecutionRequestError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ValidatedTestExecutionRequest:
    path: Path
    sha256: str
    execution_policy_sha256: str
    payload: dict[str, Any]


@contextmanager
def hold_test_execution_inputs(
    test: dict[str, Any],
    *,
    project_root: str | Path,
    artifact_root: str | Path,
) -> Iterator[None]:
    """Deny replacement or in-place writes for every byte used by one test."""
    project = lexical_absolute(project_root)
    artifacts = lexical_absolute(artifact_root)
    specs: list[StablePathSpec] = [
        StablePathSpec(
            lexical_absolute(str(test["cwd"])),
            project,
            "test execution cwd",
            directory=True,
        )
    ]
    descriptors = [test["executable"], *test["test_inputs"]]
    for index, descriptor in enumerate(descriptors):
        if not isinstance(descriptor, dict) or not isinstance(descriptor.get("path"), str):
            raise TestExecutionRequestError("test execution input descriptor is invalid")
        path = lexical_absolute(str(descriptor["path"]))
        root = next(
            (candidate for candidate in (project, artifacts) if is_within(path, candidate)),
            Path(path.anchor),
        )
        specs.append(
            StablePathSpec(path, root, f"test execution locked input {index}")
        )
    try:
        with hold_paths_stable(specs):
            _validate_test(
                test,
                index=0,
                project=project,
                artifacts=artifacts,
                label_prefix="locked test",
            )
            yield
            _validate_test(
                test,
                index=0,
                project=project,
                artifacts=artifacts,
                label_prefix="locked test",
            )
    except PathSecurityError as error:
        raise TestExecutionRequestError(str(error)) from error


def validate_test_execution_request(
    request_path: str | Path,
    *,
    project_root: str | Path,
    artifact_root: str | Path,
    project_id_hex: str,
    workflow_run_id: str,
    attempt_id: str,
    approved_test_plan_sha256: str,
    approved_test_plan_path: str | Path,
) -> ValidatedTestExecutionRequest:
    project = lexical_absolute(project_root)
    artifacts = lexical_absolute(artifact_root)
    expected = artifacts / TEST_EXECUTION_REQUEST_NAME
    path = lexical_absolute(request_path)
    if not same_path(path, expected):
        raise TestExecutionRequestError(
            f"test execution request must use the fixed path: {expected}"
        )
    try:
        raw, _identity = read_regular_file(
            path,
            allowed_root=artifacts,
            label="test execution request",
            max_bytes=4 * 1024 * 1024,
        )
        payload = json.loads(raw.decode("utf-8", errors="strict"))
    except PathSecurityError as error:
        raise TestExecutionRequestError(str(error)) from error
    except (UnicodeError, json.JSONDecodeError) as error:
        raise TestExecutionRequestError("test execution request is invalid JSON") from error
    if not isinstance(payload, dict) or set(payload) != _TOP_FIELDS:
        raise TestExecutionRequestError("test execution request has invalid fields")
    if payload["schema"] != TEST_EXECUTION_REQUEST_SCHEMA:
        raise TestExecutionRequestError("test execution request schema is unsupported")
    if _HEX_16.fullmatch(project_id_hex) is None or payload["project_id_hex"] != project_id_hex:
        raise TestExecutionRequestError("test execution request project identity differs")
    if payload["workflow_run_id"] != workflow_run_id or payload["attempt_id"] != attempt_id:
        raise TestExecutionRequestError("test execution request run identity differs")
    if (
        _HEX_32.fullmatch(approved_test_plan_sha256) is None
        or payload["approved_test_plan_sha256"] != approved_test_plan_sha256
    ):
        raise TestExecutionRequestError("test execution request plan binding differs")
    tests = payload["tests"]
    if not isinstance(tests, list) or not tests or len(tests) > 1_000:
        raise TestExecutionRequestError("test execution request has an invalid test list")
    approved_tests, execution_policy_sha256 = load_approved_test_execution_policy(
        approved_test_plan_path,
        project_root=project,
        artifact_root=artifacts,
    )
    seen_ids: set[str] = set()
    for index, test in enumerate(tests):
        test_id = _validate_test(
            test,
            index=index,
            project=project,
            artifacts=artifacts,
            label_prefix="test request",
        )
        if test_id in seen_ids:
            raise TestExecutionRequestError("test execution request repeats a test ID")
        seen_ids.add(test_id)
    if tests != approved_tests:
        raise TestExecutionRequestError(
            "test execution request differs from the reviewer-approved execution policy"
        )
    return ValidatedTestExecutionRequest(
        path=path,
        sha256=hashlib.sha256(raw).hexdigest(),
        execution_policy_sha256=execution_policy_sha256,
        payload=payload,
    )


def load_approved_test_execution_policy(
    approved_plan_path: str | Path,
    *,
    project_root: str | Path,
    artifact_root: str | Path,
) -> tuple[list[dict[str, Any]], str]:
    project = lexical_absolute(project_root)
    artifacts = lexical_absolute(artifact_root)
    path = lexical_absolute(approved_plan_path)
    root = next((candidate for candidate in (project, artifacts) if is_within(path, candidate)), None)
    if root is None:
        raise TestExecutionRequestError("approved test plan is outside allowed roots")
    try:
        raw, _identity = read_regular_file(
            path,
            allowed_root=root,
            label="approved test plan",
            max_bytes=16 * 1024 * 1024,
        )
        text = raw.decode("utf-8", errors="strict")
    except (PathSecurityError, UnicodeError) as error:
        raise TestExecutionRequestError(f"cannot read approved test plan: {error}") from error
    if text.count(TEST_EXECUTION_POLICY_BEGIN) != 1 or text.count(TEST_EXECUTION_POLICY_END) != 1:
        raise TestExecutionRequestError(
            "approved test plan must contain exactly one execution policy block"
        )
    before, remainder = text.split(TEST_EXECUTION_POLICY_BEGIN, 1)
    policy_text, after = remainder.split(TEST_EXECUTION_POLICY_END, 1)
    del before, after
    try:
        policy = json.loads(policy_text.strip())
    except json.JSONDecodeError as error:
        raise TestExecutionRequestError("approved execution policy is invalid JSON") from error
    if not isinstance(policy, dict) or set(policy) != _POLICY_FIELDS:
        raise TestExecutionRequestError("approved execution policy has invalid fields")
    if policy["schema"] != TEST_EXECUTION_POLICY_SCHEMA:
        raise TestExecutionRequestError("approved execution policy schema is unsupported")
    tests = policy["tests"]
    if not isinstance(tests, list) or not tests or len(tests) > 1_000:
        raise TestExecutionRequestError("approved execution policy has an invalid test list")
    seen_ids: set[str] = set()
    for index, test in enumerate(tests):
        test_id = _validate_test(
            test,
            index=index,
            project=project,
            artifacts=artifacts,
            label_prefix="approved test",
        )
        if test_id in seen_ids:
            raise TestExecutionRequestError("approved execution policy repeats a test ID")
        seen_ids.add(test_id)
    canonical = json.dumps(
        policy,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return tests, hashlib.sha256(canonical).hexdigest()


def _validate_test(
    test: Any,
    *,
    index: int,
    project: Path,
    artifacts: Path,
    label_prefix: str,
) -> str:
    label = f"{label_prefix} {index}"
    if not isinstance(test, dict) or set(test) != _TEST_FIELDS:
        raise TestExecutionRequestError(f"{label} has invalid fields")
    test_id = _nonempty(test["test_id"], f"{label} ID")
    _string_list(test["requirement_ids"], f"{label} requirements")
    command = _string_list(test["command"], f"{label} command")
    if len(command) > 256 or sum(len(part) for part in command) > 64 * 1024:
        raise TestExecutionRequestError(f"{label} command is too large")
    cwd_value = _nonempty(test["cwd"], f"{label} cwd")
    cwd = lexical_absolute(cwd_value)
    if not is_within(cwd, project):
        raise TestExecutionRequestError(f"{label} cwd is outside the project")
    try:
        require_no_reparse(project, cwd, label=f"{label} cwd")
    except PathSecurityError as error:
        raise TestExecutionRequestError(str(error)) from error
    if not cwd.is_dir():
        raise TestExecutionRequestError(f"{label} cwd is not a directory")
    environment = test["environment"]
    if (
        not isinstance(environment, dict)
        or len(environment) > 128
        or not all(
            isinstance(key, str)
            and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", key)
            and isinstance(value, str)
            and len(value) <= 32 * 1024
            and "\x00" not in value
            for key, value in environment.items()
        )
    ):
        raise TestExecutionRequestError(f"{label} environment is invalid")
    if environment.get("PYTHONDONTWRITEBYTECODE") != "1":
        raise TestExecutionRequestError(
            f"{label} environment must disable Python bytecode writes"
        )
    timeout = test["timeout_seconds"]
    if isinstance(timeout, bool) or not isinstance(timeout, int) or not 1 <= timeout <= 7_200:
        raise TestExecutionRequestError(f"{label} timeout is invalid")
    inputs = test["test_inputs"]
    if not isinstance(inputs, list) or not inputs or len(inputs) > 10_000:
        raise TestExecutionRequestError(f"{label} inputs are invalid")
    input_paths: set[str] = set()
    for descriptor_index, descriptor in enumerate(inputs):
        input_path = _validate_descriptor(
            descriptor,
            project=project,
            artifacts=artifacts,
            label=f"{label} input {descriptor_index}",
        )
        input_paths.add(str(input_path).casefold())
    executable_path = _validate_descriptor(
        test["executable"],
        project=project,
        artifacts=artifacts,
        label=f"{label} executable",
        allow_external_executable=True,
    )
    if not same_path(executable_path, command[0]):
        raise TestExecutionRequestError(f"{label} command executable differs from its descriptor")
    executable_name = executable_path.name.casefold()
    if executable_name in _SHELL_EXECUTABLES:
        raise TestExecutionRequestError(f"{label} invokes a forbidden shell executable")
    forbidden_flags = _INLINE_FLAGS.get(executable_name, set())
    if any(argument.casefold() in forbidden_flags for argument in command[1:]):
        raise TestExecutionRequestError(f"{label} uses inline or module code execution")
    _require_command_entry_inputs(command, cwd=cwd, input_paths=input_paths, label=label)
    return test_id


def _require_command_entry_inputs(
    command: list[str], *, cwd: Path, input_paths: set[str], label: str
) -> None:
    for argument in command[1:]:
        if argument.startswith("-") or "\x00" in argument:
            continue
        candidate = Path(argument)
        path = lexical_absolute(candidate if candidate.is_absolute() else cwd / candidate)
        if path.exists() and path.is_dir() and not same_path(path, cwd):
            raise TestExecutionRequestError(
                f"{label} references an unbound input directory: {argument}"
            )
        requires_binding = path.is_file() or (
            candidate.suffix.casefold() in _EXECUTABLE_INPUT_SUFFIXES
        )
        if requires_binding and str(path).casefold() not in input_paths:
            raise TestExecutionRequestError(
                f"{label} executable entry input is not hash-bound: {argument}"
            )


def _validate_descriptor(
    value: Any,
    *,
    project: Path,
    artifacts: Path,
    label: str,
    allow_external_executable: bool = False,
) -> Path:
    if not isinstance(value, dict) or set(value) != _DESCRIPTOR_FIELDS:
        raise TestExecutionRequestError(f"{label} descriptor is invalid")
    raw_path = value["path"]
    if not isinstance(raw_path, str) or not Path(raw_path).is_absolute():
        raise TestExecutionRequestError(f"{label} path is invalid")
    path = lexical_absolute(raw_path)
    roots = (project, artifacts)
    root = next((candidate for candidate in roots if is_within(path, candidate)), None)
    if root is None and allow_external_executable:
        root = Path(path.anchor)
    if root is None:
        raise TestExecutionRequestError(f"{label} is outside allowed roots")
    try:
        content, _identity = read_regular_file(path, allowed_root=root, label=label)
    except PathSecurityError as error:
        raise TestExecutionRequestError(str(error)) from error
    if (
        isinstance(value["size"], bool)
        or not isinstance(value["size"], int)
        or value["size"] != len(content)
        or not isinstance(value["sha256"], str)
        or _HEX_32.fullmatch(value["sha256"]) is None
        or value["sha256"] != hashlib.sha256(content).hexdigest()
    ):
        raise TestExecutionRequestError(f"{label} descriptor does not match")
    return path


def _nonempty(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TestExecutionRequestError(f"{label} is empty")
    return value


def _string_list(value: Any, label: str) -> list[str]:
    if (
        not isinstance(value, list)
        or not value
        or len(value) != len(set(value))
        or not all(isinstance(item, str) and item.strip() for item in value)
    ):
        raise TestExecutionRequestError(f"{label} is invalid")
    return value
