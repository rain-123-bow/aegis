from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
from contextlib import contextmanager
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from uuid import uuid4

from path_security import (
    PathSecurityError,
    read_regular_file,
    require_no_reparse,
)

REGISTRY_SCHEMA = "aegis.dynamic_agent_registry.v2"
REGISTRY_RELATIVE_PATH = Path("project_state/dynamic_agent_registry.json")
REGISTRY_DATABASE_RELATIVE_PATH = Path("project_state/dynamic_agent_registry.sqlite3")
_LEGACY_REGISTRY_SCHEMA = "aegis.dynamic_agent_registry.v1"
_IDENTIFIER_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


class RegistryError(RuntimeError):
    pass


class _ProcessNotFound(RegistryError):
    pass


Mutation = Callable[[dict[str, object]], object]


class DynamicAgentRegistry:
    """Transactional project registry and one-active-run lease.

    SQLite is authoritative. The JSON file is a human-readable projection only.
    Every mutation reloads the latest revision under BEGIN IMMEDIATE, so separate
    Coordinator processes cannot overwrite one another with stale in-memory data.
    """

    def __init__(self, runtime_root: str | Path, *, project_id: str) -> None:
        if _IDENTIFIER_PATTERN.fullmatch(project_id) is None:
            raise ValueError("project_id has unsupported characters")
        self.runtime_root = Path(runtime_root).resolve()
        self.project_id = project_id
        self.instance_id = uuid4().hex
        self.owner_pid = os.getpid()
        self.owner_process_identity = _process_identity(self.owner_pid)
        self.path = self.runtime_root / REGISTRY_RELATIVE_PATH
        self.database_path = self.runtime_root / REGISTRY_DATABASE_RELATIVE_PATH
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            require_no_reparse(
                self.runtime_root,
                self.database_path.parent,
                label="dynamic agent registry directory",
            )
        except PathSecurityError as error:
            raise RegistryError(str(error)) from error
        self._initialize_database()
        self._write_projection()

    def active(self, role_key: str) -> dict[str, object] | None:
        role = self._role_state(self._read_data(), role_key, create=False)
        if role is None:
            return None
        current = role.get("current")
        if not isinstance(current, dict) or current.get("lifecycle") != "active":
            return None
        return deepcopy(current)

    def retired(self, role_key: str) -> list[dict[str, object]]:
        role = self._role_state(self._read_data(), role_key, create=False)
        if role is None:
            return []
        retired = role.get("retired")
        if not isinstance(retired, list):
            raise RegistryError("registry role has invalid retired history")
        return deepcopy(retired)

    def acquire_project_lease(self, run_id: str) -> None:
        _require_identifier(run_id, "run_id")
        now = _utc_now_text()
        try:
            with self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    """
                    SELECT run_id, owner_instance_id, owner_pid, owner_process_identity
                    FROM project_run_lease WHERE project_id = ?
                    """,
                    (self.project_id,),
                ).fetchone()
                if row is not None and row[1] != self.instance_id:
                    if _process_owner_is_alive(int(row[2]), str(row[3])):
                        raise RegistryError(
                            "project is leased by active coordinator "
                            f"{row[0]} owner={row[1]}; parallel acquisition is forbidden"
                        )
                    connection.execute(
                        "DELETE FROM project_run_lease WHERE project_id = ?",
                        (self.project_id,),
                    )
                connection.execute(
                    """
                    INSERT INTO project_run_lease(
                        project_id, run_id, owner_instance_id, owner_pid,
                        owner_process_identity, acquired_at_utc, updated_at_utc
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(project_id) DO UPDATE SET
                        run_id = excluded.run_id,
                        owner_instance_id = excluded.owner_instance_id,
                        owner_pid = excluded.owner_pid,
                        owner_process_identity = excluded.owner_process_identity,
                        acquired_at_utc = excluded.acquired_at_utc,
                        updated_at_utc = excluded.updated_at_utc
                    """,
                    (
                        self.project_id,
                        run_id,
                        self.instance_id,
                        self.owner_pid,
                        self.owner_process_identity,
                        now,
                        now,
                    ),
                )
                connection.commit()
        except RegistryError:
            raise
        except sqlite3.Error as error:
            raise RegistryError(f"cannot acquire project run lease: {error}") from error

    def release_project_lease(self, run_id: str) -> None:
        _require_identifier(run_id, "run_id")
        try:
            with self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT run_id, owner_instance_id FROM project_run_lease WHERE project_id = ?",
                    (self.project_id,),
                ).fetchone()
                if row is None:
                    connection.commit()
                    return
                if row[0] != run_id:
                    raise RegistryError(
                        f"project lease belongs to {row[0]}, not {run_id}"
                    )
                if row[1] != self.instance_id:
                    raise RegistryError("project lease belongs to another coordinator instance")
                connection.execute(
                    "DELETE FROM project_run_lease WHERE project_id = ?",
                    (self.project_id,),
                )
                connection.commit()
        except RegistryError:
            raise
        except sqlite3.Error as error:
            raise RegistryError(f"cannot release project run lease: {error}") from error

    def heartbeat_project_lease(self, run_id: str) -> None:
        _require_identifier(run_id, "run_id")
        try:
            with self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                updated = connection.execute(
                    """
                    UPDATE project_run_lease SET updated_at_utc = ?
                    WHERE project_id = ? AND run_id = ? AND owner_instance_id = ?
                      AND owner_pid = ? AND owner_process_identity = ?
                    """,
                    (
                        _utc_now_text(),
                        self.project_id,
                        run_id,
                        self.instance_id,
                        self.owner_pid,
                        self.owner_process_identity,
                    ),
                )
                if updated.rowcount != 1:
                    raise RegistryError("project lease ownership was lost")
                connection.commit()
        except RegistryError:
            raise
        except sqlite3.Error as error:
            raise RegistryError(f"cannot heartbeat project run lease: {error}") from error

    def begin_allocation(
        self,
        role_key: str,
        *,
        developer_instructions_sha256: str,
        skill_bindings: Sequence[Mapping[str, object]],
        replaces_thread_id: str | None = None,
    ) -> dict[str, object]:
        _require_identifier(role_key, "role_key")
        _require_sha256(developer_instructions_sha256, "developer instructions")
        bindings = _validate_skill_bindings(skill_bindings)
        if replaces_thread_id is not None:
            _require_identifier(replaces_thread_id, "replaces_thread_id")

        def mutate(data: dict[str, object]) -> dict[str, object]:
            role = self._role_state(data, role_key, create=True)
            assert role is not None
            if role.get("current") is not None:
                raise RegistryError(
                    f"role already has a current allocation: {role_key}"
                )
            now = _utc_now_text()
            record: dict[str, object] = {
                "agent_id": uuid4().hex,
                "role_key": role_key,
                "lifecycle": "allocating",
                "thread_id": None,
                "model": None,
                "reasoning_effort": None,
                "developer_instructions_sha256": developer_instructions_sha256,
                "skill_bindings": bindings,
                "replaces_thread_id": replaces_thread_id,
                "created_at_utc": now,
                "updated_at_utc": now,
                "retired_at_utc": None,
                "retired_reason": None,
            }
            role["current"] = record
            return deepcopy(record)

        return self._mutate(mutate)

    def activate(
        self,
        role_key: str,
        *,
        agent_id: str,
        thread_id: str,
        model: str,
        reasoning_effort: str,
    ) -> dict[str, object]:
        _require_identifier(role_key, "role_key")
        _require_identifier(agent_id, "agent_id")
        _require_identifier(thread_id, "thread_id")
        if not model:
            raise ValueError("model must not be empty")
        if reasoning_effort not in {"low", "medium", "high", "xhigh"}:
            raise ValueError("reasoning_effort is unsupported")

        def mutate(data: dict[str, object]) -> dict[str, object]:
            role = self._role_state(data, role_key, create=False)
            current = role.get("current") if role is not None else None
            if not isinstance(current, dict):
                raise RegistryError(f"role has no current allocation: {role_key}")
            if current.get("agent_id") != agent_id:
                raise RegistryError("agent allocation identity mismatch")
            if current.get("lifecycle") != "allocating":
                raise RegistryError("only an allocating agent can become active")
            owner = self._thread_owner(data, thread_id)
            if owner is not None and owner != role_key:
                raise RegistryError(
                    f"thread already belongs to another role: {thread_id}: {owner}"
                )
            current.update(
                lifecycle="active",
                thread_id=thread_id,
                model=model,
                reasoning_effort=reasoning_effort,
                updated_at_utc=_utc_now_text(),
            )
            return deepcopy(current)

        return self._mutate(mutate)

    def retire(self, role_key: str, *, reason: str) -> dict[str, object]:
        if not reason.strip():
            raise ValueError("retirement reason must not be empty")

        def mutate(data: dict[str, object]) -> dict[str, object]:
            role = self._role_state(data, role_key, create=False)
            current = role.get("current") if role is not None else None
            if not isinstance(current, dict):
                raise RegistryError(f"role has no current agent: {role_key}")
            now = _utc_now_text()
            current.update(
                lifecycle="retired",
                updated_at_utc=now,
                retired_at_utc=now,
                retired_reason=reason,
            )
            retired = role.get("retired")
            if not isinstance(retired, list):
                raise RegistryError("registry role has invalid retired history")
            retired.append(deepcopy(current))
            role["current"] = None
            return deepcopy(current)

        return self._mutate(mutate)

    def _initialize_database(self) -> None:
        legacy = self._load_projection_if_present()
        try:
            with self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS registry_state(
                        project_id TEXT PRIMARY KEY,
                        revision INTEGER NOT NULL,
                        roles_json TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS project_run_lease(
                        project_id TEXT PRIMARY KEY,
                        run_id TEXT NOT NULL,
                        owner_instance_id TEXT NOT NULL,
                        owner_pid INTEGER NOT NULL,
                        owner_process_identity TEXT NOT NULL,
                        acquired_at_utc TEXT NOT NULL,
                        updated_at_utc TEXT NOT NULL
                    )
                    """
                )
                lease_columns = {
                    str(row[1])
                    for row in connection.execute(
                        "PRAGMA table_info(project_run_lease)"
                    ).fetchall()
                }
                lease_additions = {
                    "owner_instance_id": "TEXT",
                    "owner_pid": "INTEGER",
                    "owner_process_identity": "TEXT",
                }
                for column, declaration in lease_additions.items():
                    if column not in lease_columns:
                        connection.execute(
                            f"ALTER TABLE project_run_lease ADD COLUMN {column} {declaration}"
                        )
                connection.execute(
                    """
                    DELETE FROM project_run_lease
                    WHERE owner_instance_id IS NULL OR owner_pid IS NULL
                       OR owner_process_identity IS NULL
                    """
                )
                existing = connection.execute(
                    "SELECT project_id FROM registry_state"
                ).fetchall()
                if existing and all(row[0] != self.project_id for row in existing):
                    raise RegistryError(
                        "dynamic agent registry project identity mismatch"
                    )
                row = connection.execute(
                    "SELECT revision FROM registry_state WHERE project_id = ?",
                    (self.project_id,),
                ).fetchone()
                if row is None:
                    source = legacy or {
                        "schema": REGISTRY_SCHEMA,
                        "project_id": self.project_id,
                        "revision": 0,
                        "roles": {},
                    }
                    connection.execute(
                        "INSERT INTO registry_state(project_id, revision, roles_json) VALUES (?, ?, ?)",
                        (
                            self.project_id,
                            int(source["revision"]),
                            json.dumps(source["roles"], ensure_ascii=False, allow_nan=False),
                        ),
                    )
                connection.commit()
        except RegistryError:
            raise
        except sqlite3.Error as error:
            raise RegistryError(f"cannot initialize dynamic agent registry: {error}") from error

    def _load_projection_if_present(self) -> dict[str, object] | None:
        if not self.path.exists():
            return None
        try:
            encoded, _identity = read_regular_file(
                self.path,
                allowed_root=self.runtime_root,
                label="dynamic agent registry projection",
                max_bytes=4 * 1024 * 1024,
            )
            value = json.loads(encoded.decode("utf-8", errors="strict"))
        except PathSecurityError as error:
            raise RegistryError(str(error)) from error
        except (UnicodeError, json.JSONDecodeError) as error:
            raise RegistryError(f"cannot read dynamic agent registry: {error}") from error
        if not isinstance(value, dict):
            raise RegistryError("dynamic agent registry must be an object")
        if value.get("schema") not in {REGISTRY_SCHEMA, _LEGACY_REGISTRY_SCHEMA}:
            raise RegistryError("dynamic agent registry schema is unsupported")
        if value.get("project_id") != self.project_id:
            raise RegistryError("dynamic agent registry project identity mismatch")
        if (
            not isinstance(value.get("revision"), int)
            or not isinstance(value.get("roles"), dict)
        ):
            raise RegistryError("dynamic agent registry structure is invalid")
        value["schema"] = REGISTRY_SCHEMA
        return value

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.execute("PRAGMA busy_timeout=30000")
        connection.execute("PRAGMA synchronous=FULL")
        return connection

    @contextmanager
    def _connection(self):
        connection = self._connect()
        try:
            yield connection
        finally:
            connection.close()

    def _read_data(self) -> dict[str, object]:
        try:
            with self._connection() as connection:
                row = connection.execute(
                    "SELECT revision, roles_json FROM registry_state WHERE project_id = ?",
                    (self.project_id,),
                ).fetchone()
        except sqlite3.Error as error:
            raise RegistryError(f"cannot read dynamic agent registry: {error}") from error
        if row is None:
            raise RegistryError("dynamic agent registry project identity mismatch")
        try:
            roles = json.loads(row[1])
        except json.JSONDecodeError as error:
            raise RegistryError("dynamic agent registry roles are corrupt") from error
        if not isinstance(roles, dict):
            raise RegistryError("dynamic agent registry roles are invalid")
        return {
            "schema": REGISTRY_SCHEMA,
            "project_id": self.project_id,
            "revision": int(row[0]),
            "roles": roles,
        }

    def _mutate(self, mutation: Mutation) -> Any:
        try:
            with self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT revision, roles_json FROM registry_state WHERE project_id = ?",
                    (self.project_id,),
                ).fetchone()
                if row is None:
                    raise RegistryError(
                        "dynamic agent registry project identity mismatch"
                    )
                revision = int(row[0])
                roles = json.loads(row[1])
                if not isinstance(roles, dict):
                    raise RegistryError("dynamic agent registry roles are invalid")
                data: dict[str, object] = {
                    "schema": REGISTRY_SCHEMA,
                    "project_id": self.project_id,
                    "revision": revision,
                    "roles": roles,
                }
                result = mutation(data)
                updated = connection.execute(
                    """
                    UPDATE registry_state
                    SET revision = ?, roles_json = ?
                    WHERE project_id = ? AND revision = ?
                    """,
                    (
                        revision + 1,
                        json.dumps(roles, ensure_ascii=False, allow_nan=False),
                        self.project_id,
                        revision,
                    ),
                )
                if updated.rowcount != 1:
                    raise RegistryError("dynamic agent registry revision conflict")
                connection.commit()
        except RegistryError:
            raise
        except (sqlite3.Error, json.JSONDecodeError) as error:
            raise RegistryError(f"cannot update dynamic agent registry: {error}") from error
        self._write_projection()
        return result

    def _write_projection(self) -> None:
        try:
            with self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT revision, roles_json FROM registry_state WHERE project_id = ?",
                    (self.project_id,),
                ).fetchone()
                if row is None:
                    raise RegistryError(
                        "dynamic agent registry project identity mismatch"
                    )
                roles = json.loads(row[1])
                if not isinstance(roles, dict):
                    raise RegistryError("dynamic agent registry roles are invalid")
                data: dict[str, object] = {
                    "schema": REGISTRY_SCHEMA,
                    "project_id": self.project_id,
                    "revision": int(row[0]),
                    "roles": roles,
                }
                self._replace_projection(data)
                connection.commit()
        except RegistryError:
            raise
        except (OSError, sqlite3.Error, json.JSONDecodeError) as error:
            raise RegistryError(
                f"cannot write dynamic agent registry projection: {error}"
            ) from error

    def _replace_projection(self, data: dict[str, object]) -> None:
        try:
            require_no_reparse(
                self.runtime_root,
                self.path,
                label="dynamic agent registry projection",
                allow_missing_final=True,
            )
        except PathSecurityError as error:
            raise RegistryError(str(error)) from error
        payload = (
            json.dumps(data, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
        ).encode("utf-8")
        temporary = self.path.with_name(f".{self.path.name}.{uuid4().hex}.tmp")
        try:
            with temporary.open("xb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _role_state(
        data: dict[str, object], role_key: str, *, create: bool
    ) -> dict[str, object] | None:
        _require_identifier(role_key, "role_key")
        roles = data["roles"]
        assert isinstance(roles, dict)
        value = roles.get(role_key)
        if value is None and create:
            value = {"current": None, "retired": []}
            roles[role_key] = value
        if value is not None and not isinstance(value, dict):
            raise RegistryError("registry role state must be an object")
        return value

    @staticmethod
    def _thread_owner(data: dict[str, object], thread_id: str) -> str | None:
        roles = data["roles"]
        assert isinstance(roles, dict)
        for role_key, role in roles.items():
            if not isinstance(role, dict):
                raise RegistryError("registry role state must be an object")
            candidates: list[object] = [role.get("current")]
            retired = role.get("retired", [])
            if not isinstance(retired, list):
                raise RegistryError("registry retired history must be a list")
            candidates.extend(retired)
            if any(
                isinstance(candidate, dict)
                and candidate.get("thread_id") == thread_id
                for candidate in candidates
            ):
                return str(role_key)
        return None


def _validate_skill_bindings(
    bindings: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    validated: list[dict[str, object]] = []
    for binding in bindings:
        name = binding.get("name")
        version = binding.get("version")
        sha256 = binding.get("sha256")
        if not isinstance(name, str) or not name:
            raise ValueError("skill binding name must not be empty")
        if not isinstance(version, str) or not version:
            raise ValueError("skill binding version must not be empty")
        _require_sha256(sha256, "skill binding")
        validated.append({"name": name, "version": version, "sha256": sha256})
    return validated


def _require_identifier(value: object, field: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{field} has unsupported characters")
    return value


def _require_sha256(value: object, field: str) -> str:
    if not isinstance(value, str) or _SHA256_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{field} SHA-256 is invalid")
    return value


def _utc_now_text() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _process_identity(pid: int) -> str:
    if pid <= 0:
        raise RegistryError("coordinator PID is invalid")
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetProcessTimes.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
        ]
        kernel32.GetProcessTimes.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            import ctypes

            error_code = ctypes.get_last_error()
            if error_code == 87:
                raise _ProcessNotFound(f"coordinator process {pid} does not exist")
            raise RegistryError(
                f"cannot inspect coordinator process {pid}: Windows error {error_code}"
            )
        try:
            created = wintypes.FILETIME()
            exited = wintypes.FILETIME()
            kernel = wintypes.FILETIME()
            user = wintypes.FILETIME()
            if not kernel32.GetProcessTimes(
                handle,
                ctypes.byref(created),
                ctypes.byref(exited),
                ctypes.byref(kernel),
                ctypes.byref(user),
            ):
                raise RegistryError(f"cannot read coordinator process identity {pid}")
            value = (int(created.dwHighDateTime) << 32) | int(created.dwLowDateTime)
            return f"windows-filetime:{value}"
        finally:
            kernel32.CloseHandle(handle)
    stat_path = Path("/proc") / str(pid) / "stat"
    try:
        fields = stat_path.read_text(encoding="ascii").split()
        return f"proc-start:{fields[21]}"
    except FileNotFoundError as error:
        raise _ProcessNotFound(f"coordinator process {pid} does not exist") from error
    except (OSError, IndexError, UnicodeError) as error:
        raise RegistryError(f"cannot inspect coordinator process {pid}: {error}") from error


def _process_owner_is_alive(pid: int, expected_identity: str) -> bool:
    try:
        return _process_identity(pid) == expected_identity
    except _ProcessNotFound:
        return False
