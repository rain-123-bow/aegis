from __future__ import annotations

import copy
import hashlib
import inspect
import json
import os
import shutil
import subprocess
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest import mock

import rfc8785

import evaluation.aegis_v2.review_snapshot as review_snapshot_module
from evaluation.aegis_v2.review_snapshot import (
    ReviewSnapshotError,
    build_snapshot,
    snapshot_content_id,
    verify_snapshot,
    verify_snapshot_bundle,
    write_snapshot_bundle,
)


SNAPSHOT_INSTANCE_ID = "123e4567-e89b-42d3-a456-426614174000"
OTHER_SNAPSHOT_INSTANCE_ID = "123e4567-e89b-42d3-b456-426614174001"
CAPTURE_STARTED_AT_UTC = "2026-07-29T01:02:03Z"
CAPTURE_COMPLETED_AT_UTC = "2026-07-29T01:02:04Z"
SNAPSHOT_DOMAIN = b"AEGIS_REVIEW_SNAPSHOT_V1\x00"
FILE_AGGREGATE_DOMAIN = (
    b"AEGIS_REVIEW_SNAPSHOT_FILE_AGGREGATE_V1\x00"
)
GATE_WIDE_GIT_STATE_AGGREGATE_DOMAIN = (
    b"AEGIS_REVIEW_SNAPSHOT_GATE_WIDE_GIT_STATE_AGGREGATE_V1\x00"
)
REVIEW_SUBJECT_PATH = "docs/review-subject.md"
REVIEW_SUBJECT_STATE = "READY_FOR_FINAL_REVIEW"
REPOSITORY_PATHS = (
    "docs/head.txt",
    REVIEW_SUBJECT_PATH,
    "docs/staged.txt",
    "docs/tracked.txt",
    "docs/untracked.txt",
)
NON_SUBJECT_REPOSITORY_PATHS = tuple(
    path for path in REPOSITORY_PATHS if path != REVIEW_SUBJECT_PATH
)
REQUIRED_FOCUS_AREAS = (
    "POSIX_GETPATH_CONTRACT",
    "WINDOWS_HANDLE_AND_DEPLOYMENT_CONTRACT",
)
REQUIRED_ABSENT_PATHS = (
    "legacy/agent.json",
    "legacy/config.json",
)
REVIEW_PROTOCOL = {
    "review_type": "FIRST_PRINCIPLES_IMPLEMENTATION_PLAN_REVIEW",
    "pass_condition": {
        "P0": 0,
        "P1": 0,
    },
    "live_verify_required_at": [
        "REVIEW_START",
        "REVIEW_END",
    ],
    "hash_mismatch_disposition": "INVALID_REVIEW",
    "implementation_or_test_execution_claims_allowed": False,
}
REPOSITORY_EVIDENCE_COMMANDS = (
    (
        "GIT_ALLOWLIST_PATHSPEC_CACHED_DIFF_BINARY_V1",
        ("diff", "--cached", "--binary"),
        "allowlist_cached_diff_binary_sha256",
    ),
    (
        "GIT_ALLOWLIST_PATHSPEC_INDEX_LISTING_S_Z_V1",
        ("ls-files", "-s", "-z"),
        "allowlist_index_listing_s_z_sha256",
    ),
    (
        "GIT_ALLOWLIST_PATHSPEC_STATUS_PORCELAIN_V2_Z_V1",
        (
            "status",
            "--porcelain=v2",
            "-z",
            "--untracked-files=all",
        ),
        "allowlist_git_status_porcelain_v2_z_sha256",
    ),
    (
        "GIT_ALLOWLIST_PATHSPEC_TRACKED_DIFF_BINARY_V1",
        ("diff", "--binary"),
        "allowlist_tracked_diff_binary_sha256",
    ),
)
GATE_WIDE_GIT_STATE_COMMANDS = (
    (
        "GIT_GATE_WIDE_CACHED_DIFF_BINARY_V1",
        ("diff", "--cached", "--binary"),
    ),
    (
        "GIT_GATE_WIDE_INDEX_LISTING_S_Z_V1",
        ("ls-files", "-s", "-z"),
    ),
    (
        "GIT_GATE_WIDE_STATUS_PORCELAIN_V2_Z_V1",
        (
            "status",
            "--porcelain=v2",
            "-z",
            "--untracked-files=all",
        ),
    ),
    (
        "GIT_GATE_WIDE_TRACKED_DIFF_BINARY_V1",
        ("diff", "--binary"),
    ),
)


def run_git(root: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"git {' '.join(args)} failed ({result.returncode}): "
            f"{result.stderr.decode('utf-8', 'replace')}"
        )
    return result.stdout


def sha256_id(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def materialized_reviewer_repository_paths(
    repository_paths: tuple[str, ...],
    external_normative_sources: list[dict[str, Any]],
) -> tuple[str, ...]:
    combined = [
        *repository_paths,
        *(
            source["repository_path"]
            for source in external_normative_sources
        ),
    ]
    folded = [repository_path.casefold() for repository_path in combined]
    if len(combined) != len(set(folded)):
        raise AssertionError("materialized reviewer paths must be unique")
    return tuple(sorted(combined, key=lambda value: value.encode("ascii")))


def materialized_repository_evidence_commands(
    materialized_reviewer_paths: tuple[str, ...],
) -> tuple[tuple[str, tuple[str, ...], str], ...]:
    literal_pathspec = tuple(
        f":(literal){repository_path}"
        for repository_path in materialized_reviewer_paths
    )
    return tuple(
        (
            command_id,
            (*arguments, "--", *literal_pathspec),
            context_field,
        )
        for command_id, arguments, context_field in (
            REPOSITORY_EVIDENCE_COMMANDS
        )
    )


def expected_repository_evidence(
    root: Path,
    repository_paths: tuple[str, ...],
    external_normative_sources: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    materialized_paths = materialized_reviewer_repository_paths(
        repository_paths,
        external_normative_sources,
    )
    evidence: list[dict[str, Any]] = []
    for command_id, arguments, _ in (
        materialized_repository_evidence_commands(materialized_paths)
    ):
        raw = run_git(root, *arguments)
        evidence.append(
            {
                "command_id": command_id,
                "byte_size": len(raw),
                "sha256": sha256_id(raw),
            }
        )
    return evidence


def expected_gate_wide_git_state_aggregate(root: Path) -> str:
    irreversible_records: list[dict[str, Any]] = []
    for command_id, arguments in GATE_WIDE_GIT_STATE_COMMANDS:
        raw = run_git(root, *arguments)
        irreversible_records.append(
            {
                "command_id": command_id,
                "byte_size": len(raw),
                "sha256": sha256_id(raw),
            }
        )
    return sha256_id(
        GATE_WIDE_GIT_STATE_AGGREGATE_DOMAIN
        + rfc8785.dumps(irreversible_records)
    )


def parse_head_blob_identity(
    root: Path,
    repository_path: str,
) -> tuple[str | None, str | None]:
    raw = run_git(root, "ls-tree", "-z", "HEAD", "--", repository_path)
    if not raw:
        return None, None
    records = [record for record in raw.split(b"\x00") if record]
    if len(records) != 1:
        raise AssertionError(
            f"expected one HEAD tree row for {repository_path}: {records!r}"
        )
    metadata, observed_path = records[0].split(b"\t", 1)
    mode, object_type, object_id = metadata.split(b" ", 2)
    if object_type != b"blob" or observed_path.decode("utf-8") != repository_path:
        raise AssertionError(f"unexpected HEAD tree row: {records[0]!r}")
    return object_id.decode("ascii"), mode.decode("ascii")


def parse_index_blob_identity(
    root: Path,
    repository_path: str,
) -> tuple[str | None, str | None]:
    raw = run_git(root, "ls-files", "-s", "-z", "--", repository_path)
    if not raw:
        return None, None
    records = [record for record in raw.split(b"\x00") if record]
    if len(records) != 1:
        raise AssertionError(
            f"expected one index row for {repository_path}: {records!r}"
        )
    metadata, observed_path = records[0].split(b"\t", 1)
    mode, object_id, stage = metadata.split(b" ", 2)
    if stage != b"0" or observed_path.decode("utf-8") != repository_path:
        raise AssertionError(f"unexpected index row: {records[0]!r}")
    return object_id.decode("ascii"), mode.decode("ascii")


def expected_file_aggregate(files: list[dict[str, Any]]) -> str:
    return sha256_id(FILE_AGGREGATE_DOMAIN + rfc8785.dumps(files))


def expected_snapshot_content_id(snapshot: dict[str, Any]) -> str:
    unsigned = copy.deepcopy(snapshot)
    unsigned.pop("snapshot_content_id")
    return sha256_id(SNAPSHOT_DOMAIN + rfc8785.dumps(unsigned))


def resign_snapshot(
    snapshot: dict[str, Any],
    *,
    files_changed: bool = False,
) -> None:
    if files_changed:
        snapshot["file_aggregate_sha256"] = expected_file_aggregate(
            snapshot["files"]
        )
    snapshot["snapshot_content_id"] = expected_snapshot_content_id(snapshot)


def object_path(bundle_path: Path, digest: str) -> Path:
    algorithm, hex_digest = digest.split(":", 1)
    if algorithm != "sha256":
        raise AssertionError(f"unexpected digest algorithm: {algorithm}")
    return bundle_path / "objects" / "sha256" / hex_digest


class TemporaryGitRepository:
    def __init__(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self._closed = False
        self.root = Path(self._temporary_directory.name).resolve()
        run_git(self.root, "init", "--initial-branch=main")
        run_git(self.root, "config", "user.name", "Review Snapshot Test")
        run_git(
            self.root,
            "config",
            "user.email",
            "review-snapshot@example.invalid",
        )

        duplicate_bytes = b"same bytes for content-addressed deduplication\n"
        self.write("docs/head.txt", duplicate_bytes)
        self.write(
            REVIEW_SUBJECT_PATH,
            (
                b"# Test implementation plan\n\n"
                b"Status: `READY_FOR_FINAL_REVIEW`\n"
            ),
        )
        self.write("docs/staged.txt", b"staged base bytes\n")
        self.write("docs/tracked.txt", b"tracked base bytes\n")
        self.write(
            "references/frozen-duplicate.txt",
            duplicate_bytes,
        )
        self.write(
            "references/frozen-unique.txt",
            b"unique frozen normative source bytes\n",
        )
        self.write(".gitignore", b"*.ignored\n")
        run_git(self.root, "add", "--all")
        run_git(self.root, "commit", "-m", "base")

        self.write("docs/staged.txt", b"staged candidate bytes\n")
        run_git(self.root, "add", "--", "docs/staged.txt")
        self.write("docs/tracked.txt", b"tracked worktree candidate bytes\n")
        self.write("docs/untracked.txt", b"untracked candidate bytes\n")
        self.write("scratch.ignored", b"ignored and outside review domain\n")

    def close(self) -> None:
        if not self._closed:
            self._temporary_directory.cleanup()
            self._closed = True

    def write(self, repository_path: str, raw: bytes) -> None:
        destination = self.root.joinpath(*repository_path.split("/"))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)

    def read(self, repository_path: str) -> bytes:
        return self.root.joinpath(*repository_path.split("/")).read_bytes()

    def external_normative_sources(self) -> list[dict[str, Any]]:
        specifications = (
            (
                "CPYTHON-GETPATH-3.12.3",
                "references/frozen-duplicate.txt",
                "text/plain",
            ),
            (
                "WINDOWS-HANDLE-CONTRACT-V1",
                "references/frozen-unique.txt",
                "text/plain",
            ),
        )
        result: list[dict[str, Any]] = []
        for source_id, repository_path, media_type in specifications:
            raw = self.read(repository_path)
            digest = sha256_id(raw)
            result.append(
                {
                    "source_id": source_id,
                    "immutable_locator": (
                        "urn:sha256:" + digest.removeprefix("sha256:")
                    ),
                    "media_type": media_type,
                    "retrieved_at_utc": "2026-07-28T16:00:00Z",
                    "repository_path": repository_path,
                    "byte_size": len(raw),
                    "sha256": digest,
                }
            )
        return result


class ReviewSnapshotFixture:
    repository: TemporaryGitRepository

    def setUp(self) -> None:
        self.repository = TemporaryGitRepository()

    def tearDown(self) -> None:
        self.repository.close()

    def build(self) -> dict[str, Any]:
        return build_snapshot(
            self.repository.root,
            REPOSITORY_PATHS,
            snapshot_instance_id=SNAPSHOT_INSTANCE_ID,
            capture_started_at_utc=CAPTURE_STARTED_AT_UTC,
            capture_completed_at_utc=CAPTURE_COMPLETED_AT_UTC,
            required_focus_areas=REQUIRED_FOCUS_AREAS,
            required_absent_paths=REQUIRED_ABSENT_PATHS,
            external_normative_sources=(
                self.repository.external_normative_sources()
            ),
            review_subject_path=REVIEW_SUBJECT_PATH,
        )


class ReviewSnapshotTestCase(ReviewSnapshotFixture, unittest.TestCase):
    def test_build_captures_allowlist_files_git_context_and_full_self_hash(
        self,
    ) -> None:
        snapshot = self.build()

        self.assertTrue(issubclass(ReviewSnapshotError, Exception))
        self.assertEqual("ReviewSnapshot.v1", snapshot["schema_version"])
        self.assertEqual(
            SNAPSHOT_INSTANCE_ID,
            snapshot["snapshot_instance_id"],
        )
        self.assertEqual(
            4,
            uuid.UUID(snapshot["snapshot_instance_id"]).version,
        )
        self.assertEqual(
            CAPTURE_STARTED_AT_UTC,
            snapshot["capture_started_at_utc"],
        )
        self.assertEqual(
            CAPTURE_COMPLETED_AT_UTC,
            snapshot["capture_completed_at_utc"],
        )
        self.assertEqual(
            {
                "mode": "ALLOWLIST_ONLY",
                "repository_paths": list(REPOSITORY_PATHS),
                "required_focus_areas": list(REQUIRED_FOCUS_AREAS),
                "required_absent_paths": list(REQUIRED_ABSENT_PATHS),
            },
            snapshot["review_domain"],
        )

        files = snapshot["files"]
        self.assertEqual(
            list(REPOSITORY_PATHS),
            [entry["repository_path"] for entry in files],
        )
        self.assertEqual(
            sorted(REPOSITORY_PATHS, key=lambda item: item.encode("ascii")),
            [entry["repository_path"] for entry in files],
        )
        self.assertEqual(
            [
                "HEAD_BLOB",
                "HEAD_BLOB",
                "TRACKED_WORKTREE",
                "TRACKED_WORKTREE",
                "WORKTREE_UNTRACKED",
            ],
            [entry["source_kind"] for entry in files],
        )
        for entry in files:
            raw = self.repository.read(entry["repository_path"])
            self.assertEqual(len(raw), entry["byte_size"])
            self.assertEqual(sha256_id(raw), entry["sha256"])
        self.assertEqual(
            expected_file_aggregate(files),
            snapshot["file_aggregate_sha256"],
        )

        context = snapshot["repository_context"]
        external_sources = self.repository.external_normative_sources()
        materialized_paths = materialized_reviewer_repository_paths(
            REPOSITORY_PATHS,
            external_sources,
        )
        expected_allowlist_context = {
            context_field: sha256_id(
                run_git(self.repository.root, *arguments)
            )
            for _, arguments, context_field in (
                materialized_repository_evidence_commands(
                    materialized_paths
                )
            )
        }
        expected_context = {
            "head_commit": run_git(
                self.repository.root,
                "rev-parse",
                "--verify",
                "HEAD",
            )
            .decode("ascii")
            .strip(),
            "head_tree": run_git(
                self.repository.root,
                "rev-parse",
                "--verify",
                "HEAD^{tree}",
            )
            .decode("ascii")
            .strip(),
            "branch": run_git(
                self.repository.root,
                "symbolic-ref",
                "--quiet",
                "--short",
                "HEAD",
            )
            .decode("utf-8")
            .strip(),
            "git_object_format": run_git(
                self.repository.root,
                "rev-parse",
                "--show-object-format",
            )
            .decode("ascii")
            .strip(),
            "gate_wide_git_state_aggregate_sha256": (
                expected_gate_wide_git_state_aggregate(
                    self.repository.root
                )
            ),
            **expected_allowlist_context,
        }
        self.assertEqual(expected_context, context)

        self.assertEqual(
            external_sources,
            snapshot["external_normative_sources"],
        )
        expected_content_id = expected_snapshot_content_id(snapshot)
        self.assertEqual(expected_content_id, snapshot["snapshot_content_id"])
        self.assertEqual(expected_content_id, snapshot_content_id(snapshot))
        receipt = verify_snapshot(
            snapshot,
            self.repository.root,
            boundary="REVIEW_START",
        )
        self.assertEqual(
            snapshot["snapshot_content_id"],
            receipt.snapshot_content_id,
        )

    def test_manifest_binds_fixed_final_review_protocol_and_rejects_drift(
        self,
    ) -> None:
        snapshot = self.build()
        self.assertIn(
            "review_protocol",
            snapshot,
            "final-review protocol must be part of the self-hashed manifest",
        )
        self.assertEqual(REVIEW_PROTOCOL, snapshot["review_protocol"])

        mutations = (
            lambda value: value["review_protocol"].__setitem__(
                "review_type",
                "AUTHOR_SELF_REVIEW",
            ),
            lambda value: value["review_protocol"][
                "pass_condition"
            ].__setitem__("P1", 1),
            lambda value: value["review_protocol"].__setitem__(
                "live_verify_required_at",
                ["REVIEW_START"],
            ),
            lambda value: value["review_protocol"].__setitem__(
                "hash_mismatch_disposition",
                "CONTINUE_WITH_WARNING",
            ),
            lambda value: value["review_protocol"].__setitem__(
                "implementation_or_test_execution_claims_allowed",
                True,
            ),
        )
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                tampered = copy.deepcopy(snapshot)
                mutate(tampered)
                resign_snapshot(tampered)
                with self.assertRaises(ReviewSnapshotError):
                    verify_snapshot(
                        tampered,
                        self.repository.root,
                        boundary="REVIEW_START",
                    )

    def test_ready_review_subject_is_allowlisted_and_self_hashed(self) -> None:
        parameters = inspect.signature(build_snapshot).parameters
        self.assertIn(
            "review_subject_path",
            parameters,
            "build_snapshot lacks the mechanical review-subject gate",
        )
        self.assertIs(
            inspect.Parameter.empty,
            parameters["review_subject_path"].default,
            "a final-review snapshot must not make its subject optional",
        )
        snapshot = self.build()
        self.assertEqual(
            {
                "repository_path": REVIEW_SUBJECT_PATH,
                "required_state": REVIEW_SUBJECT_STATE,
                "observed_state": REVIEW_SUBJECT_STATE,
            },
            snapshot["review_subject"],
        )

        mutations = (
            lambda value: value["review_subject"].__setitem__(
                "repository_path",
                "docs/head.txt",
            ),
            lambda value: value["review_subject"].__setitem__(
                "required_state",
                "ROUND_11_CONTRACT_AND_SNAPSHOT_RECONCILIATION_IN_PROGRESS",
            ),
            lambda value: value["review_subject"].__setitem__(
                "observed_state",
                "ROUND_11_CONTRACT_AND_SNAPSHOT_RECONCILIATION_IN_PROGRESS",
            ),
        )
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                tampered = copy.deepcopy(snapshot)
                mutate(tampered)
                resign_snapshot(tampered)
                with self.assertRaises(ReviewSnapshotError):
                    verify_snapshot(
                        tampered,
                        self.repository.root,
                        boundary="REVIEW_START",
                    )

    def test_review_subject_parameter_is_mandatory(self) -> None:
        parameters = inspect.signature(build_snapshot).parameters
        self.assertIn(
            "review_subject_path",
            parameters,
            "build_snapshot lacks the mechanical review-subject gate",
        )
        self.assertIs(
            inspect.Parameter.empty,
            parameters["review_subject_path"].default,
            "review_subject_path must not have a default",
        )
        with self.assertRaises(TypeError):
            build_snapshot(
                self.repository.root,
                REPOSITORY_PATHS,
                snapshot_instance_id=SNAPSHOT_INSTANCE_ID,
                capture_started_at_utc=CAPTURE_STARTED_AT_UTC,
                capture_completed_at_utc=CAPTURE_COMPLETED_AT_UTC,
                required_focus_areas=REQUIRED_FOCUS_AREAS,
                required_absent_paths=REQUIRED_ABSENT_PATHS,
                external_normative_sources=(
                    self.repository.external_normative_sources()
                ),
            )

    def test_review_subject_must_be_ready_and_have_one_canonical_status(
        self,
    ) -> None:
        self.assertIn(
            "review_subject_path",
            inspect.signature(build_snapshot).parameters,
            "build_snapshot lacks the mechanical review-subject gate",
        )
        invalid_subjects = (
            (
                "not ready",
                (
                    b"# Test implementation plan\n\n"
                    b"Status: "
                    b"`ROUND_11_CONTRACT_AND_SNAPSHOT_RECONCILIATION_IN_PROGRESS`\n"
                ),
            ),
            (
                "missing status",
                b"# Test implementation plan\n",
            ),
            (
                "duplicate status",
                (
                    b"# Test implementation plan\n\n"
                    b"Status: `READY_FOR_FINAL_REVIEW`\n"
                    b"Status: `READY_FOR_FINAL_REVIEW`\n"
                ),
            ),
        )
        for label, raw in invalid_subjects:
            with self.subTest(label=label):
                self.repository.write(REVIEW_SUBJECT_PATH, raw)
                with self.assertRaises(ReviewSnapshotError):
                    self.build()

    def test_review_subject_must_be_inside_the_allowlist(self) -> None:
        self.assertIn(
            "review_subject_path",
            inspect.signature(build_snapshot).parameters,
            "build_snapshot lacks the mechanical review-subject gate",
        )
        with self.assertRaises(ReviewSnapshotError):
            build_snapshot(
                self.repository.root,
                NON_SUBJECT_REPOSITORY_PATHS,
                snapshot_instance_id=SNAPSHOT_INSTANCE_ID,
                capture_started_at_utc=CAPTURE_STARTED_AT_UTC,
                capture_completed_at_utc=CAPTURE_COMPLETED_AT_UTC,
                required_focus_areas=REQUIRED_FOCUS_AREAS,
                required_absent_paths=REQUIRED_ABSENT_PATHS,
                external_normative_sources=(
                    self.repository.external_normative_sources()
                ),
                review_subject_path=REVIEW_SUBJECT_PATH,
            )

    def test_instance_and_capture_times_are_inside_the_self_hash(self) -> None:
        original = self.build()
        mutations = {
            "snapshot instance": (
                "snapshot_instance_id",
                OTHER_SNAPSHOT_INSTANCE_ID,
            ),
            "capture start": (
                "capture_started_at_utc",
                "2026-07-29T01:02:02Z",
            ),
            "capture completion": (
                "capture_completed_at_utc",
                "2026-07-29T01:02:05Z",
            ),
        }
        for label, (key, value) in mutations.items():
            with self.subTest(label=label):
                tampered = copy.deepcopy(original)
                tampered[key] = value
                self.assertNotEqual(
                    original["snapshot_content_id"],
                    snapshot_content_id(tampered),
                )
                with self.assertRaises(ReviewSnapshotError):
                    verify_snapshot(
                        tampered,
                        self.repository.root,
                        boundary="REVIEW_START",
                    )

    def test_repository_evidence_binds_exact_allowlist_git_preimages(
        self,
    ) -> None:
        snapshot = self.build()
        self.assertIn(
            "repository_evidence",
            snapshot,
            "allowlist Git evidence preimages are absent from the manifest",
        )
        materialized_paths = materialized_reviewer_repository_paths(
            REPOSITORY_PATHS,
            self.repository.external_normative_sources(),
        )
        self.assertEqual(
            (
                "docs/head.txt",
                "docs/review-subject.md",
                "docs/staged.txt",
                "docs/tracked.txt",
                "docs/untracked.txt",
                "references/frozen-duplicate.txt",
                "references/frozen-unique.txt",
            ),
            materialized_paths,
        )
        expected = expected_repository_evidence(
            self.repository.root,
            REPOSITORY_PATHS,
            self.repository.external_normative_sources(),
        )
        self.assertEqual(expected, snapshot["repository_evidence"])

        context_fields = {
            command_id: context_field
            for command_id, _, context_field in (
                REPOSITORY_EVIDENCE_COMMANDS
            )
        }
        for entry in snapshot["repository_evidence"]:
            self.assertEqual(
                snapshot["repository_context"][
                    context_fields[entry["command_id"]]
                ],
                entry["sha256"],
            )

    def test_repository_evidence_and_gate_aggregate_reject_forgery(
        self,
    ) -> None:
        snapshot = self.build()
        self.assertIn(
            "repository_evidence",
            snapshot,
            "allowlist Git evidence preimages are absent from the manifest",
        )
        mutations = (
            lambda value: value.__setitem__(
                "repository_evidence",
                list(reversed(value["repository_evidence"])),
            ),
            lambda value: value["repository_evidence"].append(
                copy.deepcopy(value["repository_evidence"][-1])
            ),
            lambda value: value["repository_evidence"][0].__setitem__(
                "command_id",
                "GIT_UNKNOWN_COMMAND_V1",
            ),
            lambda value: value["repository_evidence"][0].__setitem__(
                "byte_size",
                value["repository_evidence"][0]["byte_size"] + 1,
            ),
            lambda value: value["repository_evidence"][0].__setitem__(
                "sha256",
                "sha256:" + "0" * 64,
            ),
            lambda value: value["repository_context"].__setitem__(
                "gate_wide_git_state_aggregate_sha256",
                "sha256:" + "0" * 64,
            ),
        )
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                tampered = copy.deepcopy(snapshot)
                mutate(tampered)
                resign_snapshot(tampered)
                with self.assertRaises(ReviewSnapshotError):
                    verify_snapshot(
                        tampered,
                        self.repository.root,
                        boundary="REVIEW_START",
                    )

    def test_file_records_bind_git_objects_modes_and_regular_file_kind(
        self,
    ) -> None:
        snapshot = self.build()
        self.assertIn(
            "git_object_format",
            snapshot["repository_context"],
            "repository context does not identify the Git object format",
        )
        self.assertEqual(
            run_git(
                self.repository.root,
                "rev-parse",
                "--show-object-format",
            )
            .decode("ascii")
            .strip(),
            snapshot["repository_context"]["git_object_format"],
        )

        provenance_fields = {
            "head_blob_oid",
            "head_blob_mode",
            "index_blob_oid",
            "index_blob_mode",
            "filesystem_kind",
        }
        for entry in snapshot["files"]:
            self.assertTrue(
                provenance_fields <= set(entry),
                f"{entry['repository_path']} lacks Git/file provenance",
            )
            head_oid, head_mode = parse_head_blob_identity(
                self.repository.root,
                entry["repository_path"],
            )
            index_oid, index_mode = parse_index_blob_identity(
                self.repository.root,
                entry["repository_path"],
            )
            self.assertEqual(head_oid, entry["head_blob_oid"])
            self.assertEqual(head_mode, entry["head_blob_mode"])
            self.assertEqual(index_oid, entry["index_blob_oid"])
            self.assertEqual(index_mode, entry["index_blob_mode"])
            self.assertEqual("REGULAR_FILE", entry["filesystem_kind"])

    def test_verify_rejects_resigned_git_and_file_identity_forgery(
        self,
    ) -> None:
        snapshot = self.build()
        self.assertIn(
            "git_object_format",
            snapshot["repository_context"],
            "repository context does not identify the Git object format",
        )
        self.assertIn(
            "head_blob_oid",
            snapshot["files"][0],
            "file records do not bind Git object identity",
        )
        mutations = (
            (
                False,
                lambda value: value["repository_context"].__setitem__(
                    "git_object_format",
                    "sha256",
                ),
            ),
            (
                True,
                lambda value: value["files"][0].__setitem__(
                    "head_blob_oid",
                    "0" * 40,
                ),
            ),
            (
                True,
                lambda value: value["files"][0].__setitem__(
                    "index_blob_mode",
                    "120000",
                ),
            ),
            (
                True,
                lambda value: value["files"][0].__setitem__(
                    "filesystem_kind",
                    "SYMLINK",
                ),
            ),
        )
        for files_changed, mutate in mutations:
            with self.subTest(mutation=mutate):
                tampered = copy.deepcopy(snapshot)
                mutate(tampered)
                resign_snapshot(
                    tampered,
                    files_changed=files_changed,
                )
                with self.assertRaises(ReviewSnapshotError):
                    verify_snapshot(
                        tampered,
                        self.repository.root,
                        boundary="REVIEW_START",
                    )

    def test_build_rejects_directory_and_link_inputs(self) -> None:
        directory_path = self.repository.root / "docs" / "directory-input"
        directory_path.mkdir()
        with self.assertRaises(ReviewSnapshotError):
            build_snapshot(
                self.repository.root,
                ("docs/directory-input", REVIEW_SUBJECT_PATH),
                snapshot_instance_id=SNAPSHOT_INSTANCE_ID,
                capture_started_at_utc=CAPTURE_STARTED_AT_UTC,
                capture_completed_at_utc=CAPTURE_COMPLETED_AT_UTC,
                required_focus_areas=REQUIRED_FOCUS_AREAS,
                review_subject_path=REVIEW_SUBJECT_PATH,
            )

        link_path = self.repository.root / "docs" / "link-input.txt"
        try:
            os.symlink(
                self.repository.root / "docs" / "head.txt",
                link_path,
            )
        except OSError as exc:
            self.skipTest(f"filesystem symlink unavailable: {exc}")
        with self.assertRaises(ReviewSnapshotError):
            build_snapshot(
                self.repository.root,
                ("docs/link-input.txt", REVIEW_SUBJECT_PATH),
                snapshot_instance_id=SNAPSHOT_INSTANCE_ID,
                capture_started_at_utc=CAPTURE_STARTED_AT_UTC,
                capture_completed_at_utc=CAPTURE_COMPLETED_AT_UTC,
                required_focus_areas=REQUIRED_FOCUS_AREAS,
                review_subject_path=REVIEW_SUBJECT_PATH,
            )

    def test_build_rejects_unmerged_index_conflict(self) -> None:
        run_git(self.repository.root, "add", "--all")
        run_git(self.repository.root, "commit", "-m", "capture fixture state")
        self.repository.write("docs/conflict.txt", b"base conflict bytes\n")
        run_git(self.repository.root, "add", "--", "docs/conflict.txt")
        run_git(self.repository.root, "commit", "-m", "add conflict base")
        run_git(self.repository.root, "branch", "conflicting-change")

        self.repository.write("docs/conflict.txt", b"main side bytes\n")
        run_git(self.repository.root, "add", "--", "docs/conflict.txt")
        run_git(self.repository.root, "commit", "-m", "main side")

        run_git(self.repository.root, "checkout", "conflicting-change")
        self.repository.write("docs/conflict.txt", b"other side bytes\n")
        run_git(self.repository.root, "add", "--", "docs/conflict.txt")
        run_git(self.repository.root, "commit", "-m", "other side")
        run_git(self.repository.root, "checkout", "main")
        merge = subprocess.run(
            ["git", "merge", "--no-edit", "conflicting-change"],
            cwd=self.repository.root,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            check=False,
        )
        self.assertNotEqual(0, merge.returncode)
        self.assertGreater(
            len(
                [
                    row
                    for row in run_git(
                        self.repository.root,
                        "ls-files",
                        "-u",
                        "-z",
                        "--",
                        "docs/conflict.txt",
                    ).split(b"\x00")
                    if row
                ]
            ),
            1,
        )

        with self.assertRaises(ReviewSnapshotError):
            build_snapshot(
                self.repository.root,
                ("docs/conflict.txt", REVIEW_SUBJECT_PATH),
                snapshot_instance_id=SNAPSHOT_INSTANCE_ID,
                capture_started_at_utc=CAPTURE_STARTED_AT_UTC,
                capture_completed_at_utc=CAPTURE_COMPLETED_AT_UTC,
                required_focus_areas=REQUIRED_FOCUS_AREAS,
                review_subject_path=REVIEW_SUBJECT_PATH,
            )

    def test_verify_rejects_every_unsigned_control_field_tamper(
        self,
    ) -> None:
        original = self.build()
        mutations = (
            ("schema_version", lambda value: value.__setitem__(
                "schema_version",
                "ReviewSnapshot.v2",
            )),
            ("review mode", lambda value: value["review_domain"].__setitem__(
                "mode",
                "REPOSITORY_WIDE",
            )),
            ("focus areas", lambda value: value["review_domain"][
                "required_focus_areas"
            ].append("UNDECLARED_FOCUS")),
            ("absence declarations", lambda value: value["review_domain"][
                "required_absent_paths"
            ].append("legacy/undeclared.json")),
            ("repository context", lambda value: value[
                "repository_context"
            ].__setitem__("branch", "forged")),
            ("file aggregate", lambda value: value.__setitem__(
                "file_aggregate_sha256",
                "sha256:" + "0" * 64,
            )),
            ("external source", lambda value: value[
                "external_normative_sources"
            ][0].__setitem__("media_type", "application/octet-stream")),
        )
        for label, mutate in mutations:
            with self.subTest(label=label):
                tampered = copy.deepcopy(original)
                mutate(tampered)
                with self.assertRaises(ReviewSnapshotError):
                    verify_snapshot(
                        tampered,
                        self.repository.root,
                        boundary="REVIEW_START",
                    )

    def test_verify_rejects_unknown_manifest_control_even_when_resigned(
        self,
    ) -> None:
        tampered = self.build()
        tampered["reviewer_claimed_pass"] = True
        resign_snapshot(tampered)

        with self.assertRaises(ReviewSnapshotError):
            verify_snapshot(
                tampered,
                self.repository.root,
                boundary="REVIEW_START",
            )

    def test_verify_rejects_resigned_path_reordering_and_duplicates(
        self,
    ) -> None:
        original = self.build()

        reordered = copy.deepcopy(original)
        reordered["review_domain"]["repository_paths"] = list(
            reversed(reordered["review_domain"]["repository_paths"])
        )
        reordered["files"] = list(reversed(reordered["files"]))
        resign_snapshot(reordered, files_changed=True)
        with self.assertRaises(ReviewSnapshotError):
            verify_snapshot(
                reordered,
                self.repository.root,
                boundary="REVIEW_START",
            )

        duplicated = copy.deepcopy(original)
        duplicated["review_domain"]["repository_paths"].append(
            duplicated["review_domain"]["repository_paths"][-1]
        )
        duplicated["files"].append(copy.deepcopy(duplicated["files"][-1]))
        resign_snapshot(duplicated, files_changed=True)
        with self.assertRaises(ReviewSnapshotError):
            verify_snapshot(
                duplicated,
                self.repository.root,
                boundary="REVIEW_START",
            )

    def test_verify_rejects_resigned_file_and_aggregate_forgery(
        self,
    ) -> None:
        forged_file = self.build()
        forged_file["files"][0]["sha256"] = "sha256:" + "0" * 64
        resign_snapshot(forged_file, files_changed=True)
        with self.assertRaises(ReviewSnapshotError):
            verify_snapshot(
                forged_file,
                self.repository.root,
                boundary="REVIEW_START",
            )

        forged_aggregate = self.build()
        forged_aggregate["file_aggregate_sha256"] = "sha256:" + "0" * 64
        resign_snapshot(forged_aggregate)
        with self.assertRaises(ReviewSnapshotError):
            verify_snapshot(
                forged_aggregate,
                self.repository.root,
                boundary="REVIEW_START",
            )

    def test_verify_rejects_selected_file_byte_tamper(self) -> None:
        snapshot = self.build()
        self.repository.write(
            "docs/tracked.txt",
            b"tampered after snapshot capture\n",
        )

        with self.assertRaises(ReviewSnapshotError):
            verify_snapshot(
                snapshot,
                self.repository.root,
                boundary="REVIEW_START",
            )

    def test_verify_rejects_git_state_change_outside_the_allowlist(
        self,
    ) -> None:
        snapshot = self.build()
        captured_allowlist_evidence = copy.deepcopy(
            snapshot["repository_evidence"]
        )
        self.repository.write(
            "outside-domain-change.txt",
            b"changes status without changing an allowlisted file\n",
        )

        self.assertEqual(
            captured_allowlist_evidence,
            expected_repository_evidence(
                self.repository.root,
                REPOSITORY_PATHS,
                self.repository.external_normative_sources(),
            ),
            "outside drift changed allowlist-scoped Git preimages",
        )
        gate_aggregate_field = (
            "gate_wide_git_state_aggregate_sha256"
        )
        self.assertIn(
            gate_aggregate_field,
            snapshot["repository_context"],
        )
        self.assertNotEqual(
            snapshot["repository_context"][gate_aggregate_field],
            expected_gate_wide_git_state_aggregate(
                self.repository.root
            ),
            "outside drift did not change the gate-wide aggregate",
        )
        with self.assertRaises(ReviewSnapshotError):
            verify_snapshot(
                snapshot,
                self.repository.root,
                boundary="REVIEW_START",
            )

    def test_build_rejects_non_ascii_or_non_canonical_paths(self) -> None:
        invalid_paths = (
            "",
            "/etc/passwd",
            "C:/Windows/System32/config/SAM",
            "docs\\head.txt",
            "docs/\x01control.txt",
            "docs/é.txt",
            "./docs/head.txt",
            "docs/../docs/head.txt",
            "docs//head.txt",
            "docs/",
        )
        for repository_path in invalid_paths:
            with self.subTest(repository_path=repr(repository_path)):
                with self.assertRaises(ReviewSnapshotError):
                    build_snapshot(
                        self.repository.root,
                        (repository_path, REVIEW_SUBJECT_PATH),
                        snapshot_instance_id=SNAPSHOT_INSTANCE_ID,
                        capture_started_at_utc=CAPTURE_STARTED_AT_UTC,
                        capture_completed_at_utc=CAPTURE_COMPLETED_AT_UTC,
                        required_focus_areas=REQUIRED_FOCUS_AREAS,
                        external_normative_sources=(),
                        review_subject_path=REVIEW_SUBJECT_PATH,
                    )

    def test_build_rejects_unsorted_duplicate_and_casefold_paths(
        self,
    ) -> None:
        invalid_path_sets = {
            "not strict UTF-8 byte order": (
                "docs/tracked.txt",
                "docs/head.txt",
                REVIEW_SUBJECT_PATH,
            ),
            "duplicate": (
                "docs/head.txt",
                "docs/head.txt",
                REVIEW_SUBJECT_PATH,
            ),
            "case-fold collision": (
                "docs/Case.txt",
                "docs/case.txt",
                REVIEW_SUBJECT_PATH,
            ),
        }
        self.repository.write("docs/Case.txt", b"case collision bytes\n")
        for label, repository_paths in invalid_path_sets.items():
            with self.subTest(label=label):
                with self.assertRaises(ReviewSnapshotError):
                    build_snapshot(
                        self.repository.root,
                        repository_paths,
                        snapshot_instance_id=SNAPSHOT_INSTANCE_ID,
                        capture_started_at_utc=CAPTURE_STARTED_AT_UTC,
                        capture_completed_at_utc=CAPTURE_COMPLETED_AT_UTC,
                        required_focus_areas=REQUIRED_FOCUS_AREAS,
                        external_normative_sources=(),
                        review_subject_path=REVIEW_SUBJECT_PATH,
                    )

    def test_required_absent_paths_use_strict_path_contract(self) -> None:
        invalid_path_sets = {
            "reordered": tuple(reversed(REQUIRED_ABSENT_PATHS)),
            "duplicate": (
                REQUIRED_ABSENT_PATHS[0],
                REQUIRED_ABSENT_PATHS[0],
            ),
            "backslash": ("legacy\\agent.json",),
            "dot segment": ("legacy/../agent.json",),
            "non-ASCII": ("legacy/代理.json",),
        }
        for label, required_absent_paths in invalid_path_sets.items():
            with self.subTest(label=label):
                with self.assertRaises(ReviewSnapshotError):
                    build_snapshot(
                        self.repository.root,
                        REPOSITORY_PATHS,
                        snapshot_instance_id=SNAPSHOT_INSTANCE_ID,
                        capture_started_at_utc=CAPTURE_STARTED_AT_UTC,
                        capture_completed_at_utc=CAPTURE_COMPLETED_AT_UTC,
                        required_focus_areas=REQUIRED_FOCUS_AREAS,
                        required_absent_paths=required_absent_paths,
                        external_normative_sources=(
                            self.repository.external_normative_sources()
                        ),
                        review_subject_path=REVIEW_SUBJECT_PATH,
                    )

    def test_build_rejects_required_absent_file_or_directory_present(
        self,
    ) -> None:
        for path_kind in ("file", "directory"):
            with self.subTest(path_kind=path_kind):
                repository_path = REQUIRED_ABSENT_PATHS[0]
                absolute_path = self.repository.root.joinpath(
                    *repository_path.split("/")
                )
                absolute_path.parent.mkdir(parents=True, exist_ok=True)
                if path_kind == "file":
                    absolute_path.write_bytes(b"must be absent\n")
                else:
                    absolute_path.mkdir()
                try:
                    with self.assertRaises(ReviewSnapshotError):
                        build_snapshot(
                            self.repository.root,
                            REPOSITORY_PATHS,
                            snapshot_instance_id=SNAPSHOT_INSTANCE_ID,
                            capture_started_at_utc=CAPTURE_STARTED_AT_UTC,
                            capture_completed_at_utc=(
                                CAPTURE_COMPLETED_AT_UTC
                            ),
                            required_focus_areas=REQUIRED_FOCUS_AREAS,
                            required_absent_paths=REQUIRED_ABSENT_PATHS,
                            external_normative_sources=(
                                self.repository.external_normative_sources()
                            ),
                            review_subject_path=REVIEW_SUBJECT_PATH,
                        )
                finally:
                    if absolute_path.is_dir():
                        absolute_path.rmdir()
                    elif absolute_path.exists():
                        absolute_path.unlink()

    def test_live_verify_rejects_required_absent_path_appearing(
        self,
    ) -> None:
        mutations = ("file", "directory")
        for path_kind in mutations:
            with self.subTest(path_kind=path_kind):
                snapshot = self.build()
                repository_path = REQUIRED_ABSENT_PATHS[-1]
                absolute_path = self.repository.root.joinpath(
                    *repository_path.split("/")
                )
                absolute_path.parent.mkdir(parents=True, exist_ok=True)
                if path_kind == "file":
                    absolute_path.write_bytes(b"appeared after capture\n")
                else:
                    absolute_path.mkdir()
                try:
                    with self.assertRaises(ReviewSnapshotError):
                        verify_snapshot(
                            snapshot,
                            self.repository.root,
                            boundary="REVIEW_START",
                        )
                finally:
                    if absolute_path.is_dir():
                        absolute_path.rmdir()
                    elif absolute_path.exists():
                        absolute_path.unlink()

    def test_verify_rejects_resigned_absence_reordering_and_duplicate(
        self,
    ) -> None:
        original = self.build()
        mutations = (
            lambda value: value["review_domain"].__setitem__(
                "required_absent_paths",
                list(
                    reversed(
                        value["review_domain"]["required_absent_paths"]
                    )
                ),
            ),
            lambda value: value["review_domain"][
                "required_absent_paths"
            ].append(
                value["review_domain"]["required_absent_paths"][-1]
            ),
        )
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                tampered = copy.deepcopy(original)
                mutate(tampered)
                resign_snapshot(tampered)
                with self.assertRaises(ReviewSnapshotError):
                    verify_snapshot(
                        tampered,
                        self.repository.root,
                        boundary="REVIEW_START",
                    )

    def test_build_rejects_absence_descendant_conflicts(
        self,
    ) -> None:
        conflicting_absence_sets = (
            ("allowlisted file descendant", ("docs/head.txt/child",)),
            (
                "external source descendant",
                ("references/frozen-unique.txt/child",),
            ),
        )
        for label, absent_paths in conflicting_absence_sets:
            with self.subTest(label=label):
                with self.assertRaises(ReviewSnapshotError):
                    build_snapshot(
                        self.repository.root,
                        REPOSITORY_PATHS,
                        snapshot_instance_id=SNAPSHOT_INSTANCE_ID,
                        capture_started_at_utc=CAPTURE_STARTED_AT_UTC,
                        capture_completed_at_utc=CAPTURE_COMPLETED_AT_UTC,
                        required_focus_areas=REQUIRED_FOCUS_AREAS,
                        required_absent_paths=absent_paths,
                        external_normative_sources=(
                            self.repository.external_normative_sources()
                        ),
                        review_subject_path=REVIEW_SUBJECT_PATH,
                    )

    def test_build_rejects_missing_or_deleted_allowlisted_file(
        self,
    ) -> None:
        for repository_path in (
            "docs/missing.txt",
            "docs/deleted.txt",
        ):
            if repository_path.endswith("deleted.txt"):
                self.repository.write(
                    repository_path,
                    b"tracked then deleted\n",
                )
                run_git(self.repository.root, "add", "--", repository_path)
                run_git(self.repository.root, "commit", "-m", "add deleted")
                self.repository.root.joinpath(
                    *repository_path.split("/")
                ).unlink()
            with self.subTest(repository_path=repository_path):
                with self.assertRaises(ReviewSnapshotError):
                    build_snapshot(
                        self.repository.root,
                        tuple(
                            sorted(
                                (repository_path, REVIEW_SUBJECT_PATH),
                                key=lambda item: item.encode("ascii"),
                            )
                        ),
                        snapshot_instance_id=SNAPSHOT_INSTANCE_ID,
                        capture_started_at_utc=CAPTURE_STARTED_AT_UTC,
                        capture_completed_at_utc=CAPTURE_COMPLETED_AT_UTC,
                        required_focus_areas=REQUIRED_FOCUS_AREAS,
                        external_normative_sources=(),
                        review_subject_path=REVIEW_SUBJECT_PATH,
                    )

    def test_build_rejects_invalid_instance_or_capture_window(self) -> None:
        invalid_arguments = (
            {
                "snapshot_instance_id": "not-a-uuid",
            },
            {
                "snapshot_instance_id": (
                    "123e4567-e89b-12d3-a456-426614174000"
                ),
            },
            {
                "capture_started_at_utc": (
                    "2026-07-29T09:02:03+08:00"
                ),
            },
            {
                "capture_completed_at_utc": (
                    "2026-07-29T01:02:02Z"
                ),
            },
        )
        defaults = {
            "snapshot_instance_id": SNAPSHOT_INSTANCE_ID,
            "capture_started_at_utc": CAPTURE_STARTED_AT_UTC,
            "capture_completed_at_utc": CAPTURE_COMPLETED_AT_UTC,
        }
        for overrides in invalid_arguments:
            with self.subTest(overrides=overrides):
                arguments = {**defaults, **overrides}
                with self.assertRaises(ReviewSnapshotError):
                    build_snapshot(
                        self.repository.root,
                        REPOSITORY_PATHS,
                        required_focus_areas=REQUIRED_FOCUS_AREAS,
                        external_normative_sources=(
                            self.repository.external_normative_sources()
                        ),
                        review_subject_path=REVIEW_SUBJECT_PATH,
                        **arguments,
                    )

    def test_external_sources_require_exact_local_frozen_bytes(self) -> None:
        valid_sources = self.repository.external_normative_sources()
        invalid_sources: list[tuple[str, list[dict[str, Any]]]] = []

        rolling_locator = copy.deepcopy(valid_sources)
        rolling_locator[0]["immutable_locator"] = (
            "https://example.invalid/spec/latest"
        )
        invalid_sources.append(("rolling URL", rolling_locator))

        wrong_size = copy.deepcopy(valid_sources)
        wrong_size[0]["byte_size"] += 1
        invalid_sources.append(("wrong byte size", wrong_size))

        wrong_hash = copy.deepcopy(valid_sources)
        wrong_hash[0]["sha256"] = "sha256:" + "0" * 64
        invalid_sources.append(("wrong hash", wrong_hash))

        missing_local_copy = copy.deepcopy(valid_sources)
        missing_local_copy[0]["repository_path"] = (
            "references/does-not-exist.txt"
        )
        invalid_sources.append(("missing local copy", missing_local_copy))

        for label, sources in invalid_sources:
            with self.subTest(label=label):
                with self.assertRaises(ReviewSnapshotError):
                    build_snapshot(
                        self.repository.root,
                        REPOSITORY_PATHS,
                        snapshot_instance_id=SNAPSHOT_INSTANCE_ID,
                        capture_started_at_utc=CAPTURE_STARTED_AT_UTC,
                        capture_completed_at_utc=CAPTURE_COMPLETED_AT_UTC,
                        required_focus_areas=REQUIRED_FOCUS_AREAS,
                        external_normative_sources=sources,
                        review_subject_path=REVIEW_SUBJECT_PATH,
                    )

    def test_external_sources_reject_reordering_duplicates_and_bad_paths(
        self,
    ) -> None:
        valid_sources = self.repository.external_normative_sources()
        invalid_sources = (
            ("reordered", list(reversed(valid_sources))),
            ("duplicate", [*valid_sources, copy.deepcopy(valid_sources[-1])]),
        )
        for label, sources in invalid_sources:
            with self.subTest(label=label):
                with self.assertRaises(ReviewSnapshotError):
                    build_snapshot(
                        self.repository.root,
                        REPOSITORY_PATHS,
                        snapshot_instance_id=SNAPSHOT_INSTANCE_ID,
                        capture_started_at_utc=CAPTURE_STARTED_AT_UTC,
                        capture_completed_at_utc=CAPTURE_COMPLETED_AT_UTC,
                        required_focus_areas=REQUIRED_FOCUS_AREAS,
                        external_normative_sources=sources,
                        review_subject_path=REVIEW_SUBJECT_PATH,
                    )

        bad_path_sources = copy.deepcopy(valid_sources)
        bad_path_sources[0]["repository_path"] = (
            "references\\frozen-duplicate.txt"
        )
        with self.assertRaises(ReviewSnapshotError):
            build_snapshot(
                self.repository.root,
                REPOSITORY_PATHS,
                snapshot_instance_id=SNAPSHOT_INSTANCE_ID,
                capture_started_at_utc=CAPTURE_STARTED_AT_UTC,
                capture_completed_at_utc=CAPTURE_COMPLETED_AT_UTC,
                required_focus_areas=REQUIRED_FOCUS_AREAS,
                external_normative_sources=bad_path_sources,
                review_subject_path=REVIEW_SUBJECT_PATH,
            )

    def test_verify_rejects_resigned_external_source_metadata_forgery(
        self,
    ) -> None:
        tampered = self.build()
        tampered["external_normative_sources"][0]["byte_size"] += 1
        resign_snapshot(tampered)

        with self.assertRaises(ReviewSnapshotError):
            verify_snapshot(
                tampered,
                self.repository.root,
                boundary="REVIEW_START",
            )

    def test_verify_rejects_resigned_external_reordering_and_duplicate(
        self,
    ) -> None:
        original = self.build()
        mutations = (
            lambda value: value.__setitem__(
                "external_normative_sources",
                list(reversed(value["external_normative_sources"])),
            ),
            lambda value: value["external_normative_sources"].append(
                copy.deepcopy(value["external_normative_sources"][-1])
            ),
        )
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                tampered = copy.deepcopy(original)
                mutate(tampered)
                resign_snapshot(tampered)
                with self.assertRaises(ReviewSnapshotError):
                    verify_snapshot(
                        tampered,
                        self.repository.root,
                        boundary="REVIEW_START",
                    )


class ReviewSnapshotBundleTestCase(
    ReviewSnapshotFixture,
    unittest.TestCase,
):
    def test_write_bundle_is_create_new_canonical_and_deduplicated(
        self,
    ) -> None:
        snapshot = self.build()
        with tempfile.TemporaryDirectory() as directory:
            destination_root = Path(directory).resolve()
            bundle_path = write_snapshot_bundle(
                snapshot,
                self.repository.root,
                destination_root,
            )

            self.assertEqual(
                destination_root / SNAPSHOT_INSTANCE_ID,
                bundle_path,
            )
            self.assertEqual(
                rfc8785.dumps(snapshot) + b"\n",
                (bundle_path / "manifest.json").read_bytes(),
            )

            expected_digests = {
                entry["sha256"]
                for entry in snapshot["files"]
            } | {
                entry["sha256"]
                for entry in snapshot["external_normative_sources"]
            } | {
                entry["sha256"]
                for entry in snapshot["repository_evidence"]
            }
            observed_objects = {
                "sha256:" + path.name
                for path in (
                    bundle_path / "objects" / "sha256"
                ).iterdir()
                if path.is_file()
            }
            self.assertEqual(expected_digests, observed_objects)
            self.assertLess(
                len(observed_objects),
                len(snapshot["files"])
                + len(snapshot["external_normative_sources"])
                + len(snapshot["repository_evidence"]),
            )

            for entry in (
                snapshot["files"]
                + snapshot["external_normative_sources"]
            ):
                self.assertEqual(
                    self.repository.read(entry["repository_path"]),
                    object_path(bundle_path, entry["sha256"]).read_bytes(),
                )
            result = verify_snapshot_bundle(
                bundle_path,
                expected_snapshot_content_id=snapshot[
                    "snapshot_content_id"
                ],
            )
            self.assertTrue(result.integrity_valid)

            with self.assertRaises(ReviewSnapshotError):
                write_snapshot_bundle(
                    snapshot,
                    self.repository.root,
                    destination_root,
                )

    def test_bundle_contains_exact_allowlist_git_evidence_and_verifies_offline(
        self,
    ) -> None:
        snapshot = self.build()
        self.assertIn(
            "repository_evidence",
            snapshot,
            "allowlist Git evidence preimages are absent from the manifest",
        )
        materialized_paths = materialized_reviewer_repository_paths(
            REPOSITORY_PATHS,
            self.repository.external_normative_sources(),
        )
        expected_raw_by_id = {
            command_id: run_git(self.repository.root, *arguments)
            for command_id, arguments, _ in (
                materialized_repository_evidence_commands(
                    materialized_paths
                )
            )
        }
        self.assertEqual(
            expected_repository_evidence(
                self.repository.root,
                REPOSITORY_PATHS,
                self.repository.external_normative_sources(),
            ),
            snapshot["repository_evidence"],
        )
        with tempfile.TemporaryDirectory() as directory:
            destination_root = Path(directory).resolve()
            bundle_path = write_snapshot_bundle(
                snapshot,
                self.repository.root,
                destination_root,
            )
            for entry in snapshot["repository_evidence"]:
                self.assertEqual(
                    expected_raw_by_id[entry["command_id"]],
                    object_path(bundle_path, entry["sha256"]).read_bytes(),
                )
            gate_aggregate = snapshot["repository_context"][
                "gate_wide_git_state_aggregate_sha256"
            ]
            self.assertNotIn(
                gate_aggregate,
                {
                    entry["sha256"]
                    for entry in snapshot["repository_evidence"]
                },
                "gate-wide aggregate must not masquerade as raw evidence",
            )
            self.assertFalse(
                object_path(bundle_path, gate_aggregate).exists(),
                "gate-wide aggregate must not be a bundle object",
            )
            evidence_object = object_path(
                bundle_path,
                snapshot["repository_evidence"][0]["sha256"],
            )
            self.assertTrue(evidence_object.is_file())
            self.repository.close()
            result = verify_snapshot_bundle(
                bundle_path,
                expected_snapshot_content_id=snapshot[
                    "snapshot_content_id"
                ],
            )
            self.assertTrue(result.integrity_valid)

    def test_bundle_rejects_missing_git_evidence_object(self) -> None:
        snapshot = self.build()
        self.assertIn(
            "repository_evidence",
            snapshot,
            "allowlist Git evidence preimages are absent from the manifest",
        )
        with tempfile.TemporaryDirectory() as directory:
            destination_root = Path(directory).resolve()
            bundle_path = write_snapshot_bundle(
                snapshot,
                self.repository.root,
                destination_root,
            )
            object_path(
                bundle_path,
                snapshot["repository_evidence"][0]["sha256"],
            ).unlink()

            with self.assertRaises(ReviewSnapshotError):
                verify_snapshot_bundle(
                    bundle_path,
                    expected_snapshot_content_id=snapshot[
                        "snapshot_content_id"
                    ],
                )

    def test_bundle_rejects_resigned_absence_ancestry_conflicts(
        self,
    ) -> None:
        conflicts = (
            ("allowlist ancestor", "docs"),
            ("allowlist descendant", "docs/head.txt/child"),
            ("external ancestor", "references"),
            (
                "external descendant",
                "references/frozen-unique.txt/child",
            ),
        )
        for label, absent_path in conflicts:
            with self.subTest(label=label):
                snapshot = self.build()
                with tempfile.TemporaryDirectory() as directory:
                    destination_root = Path(directory).resolve()
                    bundle_path = write_snapshot_bundle(
                        snapshot,
                        self.repository.root,
                        destination_root,
                    )
                    tampered = copy.deepcopy(snapshot)
                    tampered["review_domain"]["required_absent_paths"] = [
                        absent_path
                    ]
                    resign_snapshot(tampered)
                    (bundle_path / "manifest.json").write_bytes(
                        rfc8785.dumps(tampered) + b"\n"
                    )

                    with self.assertRaises(ReviewSnapshotError):
                        verify_snapshot_bundle(
                            bundle_path,
                            expected_snapshot_content_id=tampered[
                                "snapshot_content_id"
                            ],
                        )

    def test_bundle_publication_never_exposes_a_partial_target(
        self,
    ) -> None:
        snapshot = self.build()
        with tempfile.TemporaryDirectory() as directory:
            destination_root = Path(directory).resolve()
            final_target = destination_root / SNAPSHOT_INSTANCE_ID
            partial_target_observations: list[bool] = []

            def fail_at_publication_boundary(
                source: str | os.PathLike[str],
                destination: str | os.PathLike[str],
            ) -> None:
                destination_path = Path(destination)
                self.assertEqual(
                    final_target,
                    destination_path,
                    "publication helper targeted an unexpected path",
                )
                partial_target_observations.append(final_target.exists())
                raise OSError("injected exclusive-publication failure")

            with mock.patch.object(
                review_snapshot_module,
                "_rename_directory_no_replace",
                side_effect=fail_at_publication_boundary,
            ):
                with self.assertRaisesRegex(
                    ReviewSnapshotError,
                    "^bundle creation failed; staging bundle retained at: ",
                ) as raised:
                    write_snapshot_bundle(
                        snapshot,
                        self.repository.root,
                        destination_root,
                    )

            self.assertEqual(
                [False],
                partial_target_observations,
                "the final instance directory became visible while partial",
            )
            self.assertFalse(final_target.exists())
            retained_staging = list(
                destination_root.glob(".review-snapshot-*")
            )
            self.assertEqual(
                1,
                len(retained_staging),
                "failed publication did not retain exactly one staging bundle",
            )
            self.assertTrue(retained_staging[0].is_dir())
            self.assertIn(str(retained_staging[0]), str(raised.exception))
            self.assertIsNone(
                review_snapshot_module._verify_staging_snapshot_bundle_path(
                    retained_staging[0]
                )
            )

    @unittest.skipUnless(
        os.name == "posix",
        "POSIX rename semantics are required for this regression",
    )
    def test_posix_publish_race_preserves_competitor_empty_target(
        self,
    ) -> None:
        snapshot = self.build()
        with tempfile.TemporaryDirectory() as directory:
            destination_root = Path(directory).resolve()
            final_target = destination_root / SNAPSHOT_INSTANCE_ID
            real_rename_no_replace = getattr(
                review_snapshot_module,
                "_rename_directory_no_replace",
                None,
            )
            competitor_identity: tuple[int, int] | None = None

            def create_competitor_at_publish_boundary(
                source: str | os.PathLike[str],
                destination: str | os.PathLike[str],
            ) -> None:
                nonlocal competitor_identity
                if real_rename_no_replace is None:
                    self.fail(
                        "exclusive directory publish helper is unavailable"
                    )
                destination_path = Path(destination)
                if destination_path == final_target:
                    final_target.mkdir()
                    target_stat = final_target.stat()
                    competitor_identity = (
                        target_stat.st_dev,
                        target_stat.st_ino,
                    )
                real_rename_no_replace(source, destination)

            creation_error: ReviewSnapshotError | None = None
            with mock.patch.object(
                review_snapshot_module,
                "_rename_directory_no_replace",
                side_effect=create_competitor_at_publish_boundary,
                create=True,
            ):
                try:
                    write_snapshot_bundle(
                        snapshot,
                        self.repository.root,
                        destination_root,
                    )
                except ReviewSnapshotError as exc:
                    creation_error = exc

            self.assertIsNotNone(
                competitor_identity,
                "the competitor did not reach the publish boundary",
            )
            observed_stat = final_target.stat()
            self.assertEqual(
                competitor_identity,
                (observed_stat.st_dev, observed_stat.st_ino),
                "publication replaced the competitor's empty target",
            )
            self.assertEqual([], list(final_target.iterdir()))
            self.assertIsNotNone(
                creation_error,
                "publication did not fail closed after losing create-new",
            )

    def test_target_cleanup_aba_preserves_competitor_directory(
        self,
    ) -> None:
        snapshot = self.build()
        with tempfile.TemporaryDirectory() as directory:
            destination_root = Path(directory).resolve()
            final_target = destination_root / SNAPSHOT_INSTANCE_ID
            displaced_target = destination_root / "displaced-writer-target"
            competitor_marker = final_target / "competitor.marker"
            real_verify = review_snapshot_module._verify_snapshot_bundle_path
            race_injected = False

            def swap_target_before_final_verification(bundle: Path) -> None:
                nonlocal race_injected
                bundle_path = Path(bundle)
                if bundle_path == final_target:
                    os.rename(final_target, displaced_target)
                    final_target.mkdir()
                    competitor_marker.write_bytes(b"competitor-owned\n")
                    race_injected = True
                real_verify(bundle_path)

            with mock.patch.object(
                review_snapshot_module,
                "_verify_snapshot_bundle_path",
                side_effect=swap_target_before_final_verification,
            ):
                with self.assertRaises(ReviewSnapshotError):
                    write_snapshot_bundle(
                        snapshot,
                        self.repository.root,
                        destination_root,
                    )

            self.assertTrue(
                race_injected,
                "the competitor did not reach the post-publication boundary",
            )
            self.assertTrue(
                competitor_marker.is_file(),
                "cleanup deleted the competitor's replacement directory",
            )
            self.assertEqual(
                b"competitor-owned\n",
                competitor_marker.read_bytes(),
            )
            self.assertTrue(displaced_target.is_dir())

    def test_staging_bundle_aba_preserves_competitor_directory(
        self,
    ) -> None:
        snapshot = self.build()
        with tempfile.TemporaryDirectory() as directory:
            destination_root = Path(directory).resolve()
            displaced_staging = destination_root / "displaced-staging"
            captured_staging_bundle: Path | None = None
            competitor_marker: Path | None = None
            real_mkdtemp = tempfile.mkdtemp
            real_verify = (
                review_snapshot_module._verify_staging_snapshot_bundle_path
            )

            def capture_staging_bundle(
                *arguments: Any,
                **keyword_arguments: Any,
            ) -> str:
                nonlocal captured_staging_bundle
                created = real_mkdtemp(*arguments, **keyword_arguments)
                captured_staging_bundle = Path(created)
                return created

            def swap_staging_bundle_before_failure(bundle: Path) -> None:
                nonlocal competitor_marker
                bundle_path = Path(bundle)
                if (
                    captured_staging_bundle is not None
                    and bundle_path == captured_staging_bundle
                ):
                    real_verify(bundle_path)
                    os.rename(captured_staging_bundle, displaced_staging)
                    captured_staging_bundle.mkdir()
                    competitor_marker = (
                        captured_staging_bundle / "competitor.marker"
                    )
                    competitor_marker.write_bytes(b"competitor-owned\n")
                    raise ReviewSnapshotError(
                        "injected failure after staging-bundle ABA"
                    )
                real_verify(bundle_path)

            with mock.patch.object(
                review_snapshot_module.tempfile,
                "mkdtemp",
                side_effect=capture_staging_bundle,
            ), mock.patch.object(
                review_snapshot_module,
                "_verify_staging_snapshot_bundle_path",
                side_effect=swap_staging_bundle_before_failure,
            ):
                with self.assertRaisesRegex(
                    ReviewSnapshotError,
                    "staging bundle path identity changed and was left "
                    "untouched",
                ) as raised:
                    write_snapshot_bundle(
                        snapshot,
                        self.repository.root,
                        destination_root,
                    )

            self.assertFalse(
                (destination_root / SNAPSHOT_INSTANCE_ID).exists()
            )
            self.assertIsNotNone(captured_staging_bundle)
            self.assertIsNotNone(competitor_marker)
            if competitor_marker is None:
                self.fail("the competitor marker path was not captured")
            self.assertTrue(
                competitor_marker.is_file(),
                "failure handling deleted the competitor's replacement",
            )
            self.assertEqual(
                b"competitor-owned\n",
                competitor_marker.read_bytes(),
            )
            self.assertTrue(displaced_staging.is_dir())
            self.assertIsNone(
                review_snapshot_module._verify_staging_snapshot_bundle_path(
                    displaced_staging
                )
            )
            self.assertIn(
                str(captured_staging_bundle),
                str(raised.exception),
            )

    def test_post_publication_failure_never_leaves_final_name_partial(
        self,
    ) -> None:
        snapshot = self.build()
        with tempfile.TemporaryDirectory() as directory:
            destination_root = Path(directory).resolve()
            final_target = destination_root / SNAPSHOT_INSTANCE_ID
            real_verify = review_snapshot_module._verify_snapshot_bundle_path
            real_rmtree = shutil.rmtree
            final_verification_failed = False
            final_target_cleanup_attempts: list[Path] = []

            def fail_final_verification(bundle: Path) -> None:
                nonlocal final_verification_failed
                bundle_path = Path(bundle)
                if bundle_path == final_target:
                    final_verification_failed = True
                    raise ReviewSnapshotError(
                        "injected post-publication verification failure"
                    )
                real_verify(bundle_path)

            def record_forbidden_final_cleanup(
                path: str | os.PathLike[str],
                *arguments: Any,
                **keyword_arguments: Any,
            ) -> None:
                cleanup_path = Path(path)
                if cleanup_path == final_target:
                    final_target_cleanup_attempts.append(cleanup_path)
                    return
                real_rmtree(path, *arguments, **keyword_arguments)

            with mock.patch.object(
                review_snapshot_module,
                "_verify_snapshot_bundle_path",
                side_effect=fail_final_verification,
            ), mock.patch.object(
                shutil,
                "rmtree",
                side_effect=record_forbidden_final_cleanup,
            ):
                with self.assertRaisesRegex(
                    ReviewSnapshotError,
                    "^injected post-publication verification failure$",
                ):
                    write_snapshot_bundle(
                        snapshot,
                        self.repository.root,
                        destination_root,
                    )

            self.assertTrue(final_verification_failed)
            self.assertTrue(final_target.is_dir())
            self.assertEqual(
                rfc8785.dumps(snapshot) + b"\n",
                (final_target / "manifest.json").read_bytes(),
            )
            result = verify_snapshot_bundle(
                final_target,
                expected_snapshot_content_id=snapshot[
                    "snapshot_content_id"
                ],
            )
            self.assertTrue(result.integrity_valid)
            self.assertEqual(
                [],
                final_target_cleanup_attempts,
                "post-publication failure attempted pathname rollback",
            )

    def test_write_bundle_rejects_stale_snapshot_without_partial_output(
        self,
    ) -> None:
        snapshot = self.build()
        self.repository.write(
            "outside-domain-change.txt",
            b"makes the repository context stale\n",
        )
        with tempfile.TemporaryDirectory() as directory:
            destination_root = Path(directory).resolve()
            with self.assertRaises(ReviewSnapshotError):
                write_snapshot_bundle(
                    snapshot,
                    self.repository.root,
                    destination_root,
                )
            self.assertFalse(
                (destination_root / SNAPSHOT_INSTANCE_ID).exists()
            )

    def test_bundle_verification_does_not_depend_on_original_worktree(
        self,
    ) -> None:
        snapshot = self.build()
        with tempfile.TemporaryDirectory() as directory:
            destination_root = Path(directory).resolve()
            bundle_path = write_snapshot_bundle(
                snapshot,
                self.repository.root,
                destination_root,
            )
            self.repository.close()

            result = verify_snapshot_bundle(
                bundle_path,
                expected_snapshot_content_id=snapshot[
                    "snapshot_content_id"
                ],
            )
            self.assertTrue(result.integrity_valid)

    def test_offline_bundle_does_not_claim_current_worktree_absence(
        self,
    ) -> None:
        snapshot = self.build()
        with tempfile.TemporaryDirectory() as directory:
            destination_root = Path(directory).resolve()
            bundle_path = write_snapshot_bundle(
                snapshot,
                self.repository.root,
                destination_root,
            )
            appeared_path = self.repository.root.joinpath(
                *REQUIRED_ABSENT_PATHS[0].split("/")
            )
            appeared_path.parent.mkdir(parents=True, exist_ok=True)
            appeared_path.write_bytes(b"appeared after bundle capture\n")

            with self.assertRaises(ReviewSnapshotError):
                verify_snapshot(
                    snapshot,
                    self.repository.root,
                    boundary="REVIEW_START",
                )
            result = verify_snapshot_bundle(
                bundle_path,
                expected_snapshot_content_id=snapshot[
                    "snapshot_content_id"
                ],
            )
            self.assertTrue(result.integrity_valid)
            self.assertEqual(
                "UNVERIFIED",
                result.live_verification_state,
            )
            self.assertEqual(
                "NOT_AUTHORIZED",
                result.authorization_state,
            )

    def test_bundle_directory_name_must_equal_snapshot_instance_id(
        self,
    ) -> None:
        snapshot = self.build()
        with tempfile.TemporaryDirectory() as directory:
            destination_root = Path(directory).resolve()
            bundle_path = write_snapshot_bundle(
                snapshot,
                self.repository.root,
                destination_root,
            )
            renamed_path = destination_root / "wrong-instance"
            bundle_path.rename(renamed_path)

            with self.assertRaises(ReviewSnapshotError):
                verify_snapshot_bundle(
                    renamed_path,
                    expected_snapshot_content_id=snapshot[
                        "snapshot_content_id"
                    ],
                )

    def test_bundle_rejects_tampered_missing_and_extra_objects(self) -> None:
        mutation_names = ("tampered", "missing", "extra")
        for mutation_name in mutation_names:
            with self.subTest(mutation=mutation_name):
                snapshot = self.build()
                with tempfile.TemporaryDirectory() as directory:
                    destination_root = Path(directory).resolve()
                    bundle_path = write_snapshot_bundle(
                        snapshot,
                        self.repository.root,
                        destination_root,
                    )
                    first_object = object_path(
                        bundle_path,
                        snapshot["files"][0]["sha256"],
                    )
                    if mutation_name == "tampered":
                        first_object.write_bytes(b"tampered object bytes\n")
                    elif mutation_name == "missing":
                        first_object.unlink()
                    else:
                        extra = (
                            bundle_path
                            / "objects"
                            / "sha256"
                            / ("0" * 64)
                        )
                        extra.write_bytes(b"unreferenced object\n")

                    with self.assertRaises(ReviewSnapshotError):
                        verify_snapshot_bundle(
                            bundle_path,
                            expected_snapshot_content_id=snapshot[
                                "snapshot_content_id"
                            ],
                        )

    def test_bundle_rejects_noncanonical_or_tampered_manifest(self) -> None:
        mutation_names = ("pretty JSON", "missing LF", "tampered value")
        for mutation_name in mutation_names:
            with self.subTest(mutation=mutation_name):
                snapshot = self.build()
                with tempfile.TemporaryDirectory() as directory:
                    destination_root = Path(directory).resolve()
                    bundle_path = write_snapshot_bundle(
                        snapshot,
                        self.repository.root,
                        destination_root,
                    )
                    manifest_path = bundle_path / "manifest.json"
                    if mutation_name == "pretty JSON":
                        manifest_path.write_bytes(
                            json.dumps(
                                snapshot,
                                ensure_ascii=False,
                                indent=2,
                            ).encode("utf-8")
                            + b"\n"
                        )
                    elif mutation_name == "missing LF":
                        manifest_path.write_bytes(rfc8785.dumps(snapshot))
                    else:
                        tampered = copy.deepcopy(snapshot)
                        tampered["capture_completed_at_utc"] = (
                            "2026-07-29T01:02:05Z"
                        )
                        manifest_path.write_bytes(
                            rfc8785.dumps(tampered) + b"\n"
                        )

                    with self.assertRaises(ReviewSnapshotError):
                        verify_snapshot_bundle(
                            bundle_path,
                            expected_snapshot_content_id=snapshot[
                                "snapshot_content_id"
                            ],
                        )

    def test_bundle_rejects_unexpected_files_outside_object_store(
        self,
    ) -> None:
        snapshot = self.build()
        with tempfile.TemporaryDirectory() as directory:
            destination_root = Path(directory).resolve()
            bundle_path = write_snapshot_bundle(
                snapshot,
                self.repository.root,
                destination_root,
            )
            (bundle_path / "reviewer-note.txt").write_bytes(
                b"unbound bundle content\n"
            )

            with self.assertRaises(ReviewSnapshotError):
                verify_snapshot_bundle(
                    bundle_path,
                    expected_snapshot_content_id=snapshot[
                        "snapshot_content_id"
                    ],
                )

    def test_copied_bundle_remains_self_contained(self) -> None:
        snapshot = self.build()
        with tempfile.TemporaryDirectory() as source_directory:
            source_root = Path(source_directory).resolve()
            bundle_path = write_snapshot_bundle(
                snapshot,
                self.repository.root,
                source_root,
            )
            with tempfile.TemporaryDirectory() as copied_directory:
                copied_root = Path(copied_directory).resolve()
                copied_bundle = copied_root / bundle_path.name
                shutil.copytree(bundle_path, copied_bundle)

                result = verify_snapshot_bundle(
                    copied_bundle,
                    expected_snapshot_content_id=snapshot[
                        "snapshot_content_id"
                    ],
                )
                self.assertTrue(result.integrity_valid)


class ReviewSnapshotSecurityContractTestCase(unittest.TestCase):
    def _new_repository(self) -> TemporaryGitRepository:
        repository = TemporaryGitRepository()
        self.addCleanup(repository.close)
        return repository

    def _build(
        self,
        repository: TemporaryGitRepository,
    ) -> dict[str, Any]:
        return build_snapshot(
            repository.root,
            REPOSITORY_PATHS,
            snapshot_instance_id=SNAPSHOT_INSTANCE_ID,
            capture_started_at_utc=CAPTURE_STARTED_AT_UTC,
            capture_completed_at_utc=CAPTURE_COMPLETED_AT_UTC,
            required_focus_areas=REQUIRED_FOCUS_AREAS,
            required_absent_paths=REQUIRED_ABSENT_PATHS,
            external_normative_sources=(
                repository.external_normative_sources()
            ),
            review_subject_path=REVIEW_SUBJECT_PATH,
        )

    def _clean_git_environment(self) -> dict[str, str]:
        return {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("GIT_")
        }

    def _assert_git_environment_rejected_or_ignored(
        self,
        repository: TemporaryGitRepository,
        baseline: dict[str, Any],
        clean_environment: dict[str, str],
        contamination: dict[str, str],
    ) -> None:
        environment = {
            **clean_environment,
            **contamination,
        }
        with mock.patch.dict(os.environ, environment, clear=True):
            try:
                observed = self._build(repository)
            except ReviewSnapshotError:
                return
        self.assertEqual(
            baseline,
            observed,
            "Git control environment changed snapshot capture",
        )

    def _required_keyword_only_parameter(
        self,
        function: Any,
        parameter_name: str,
    ) -> inspect.Parameter:
        parameter = inspect.signature(function).parameters.get(
            parameter_name
        )
        self.assertIsNotNone(
            parameter,
            f"{function.__name__} lacks {parameter_name}",
        )
        if parameter is None:
            self.fail(f"{function.__name__} lacks {parameter_name}")
        self.assertEqual(
            inspect.Parameter.KEYWORD_ONLY,
            parameter.kind,
        )
        self.assertIs(
            inspect.Parameter.empty,
            parameter.default,
        )
        return parameter

    def _required_result_type(self, name: str) -> type[Any]:
        result_type = getattr(review_snapshot_module, name, None)
        self.assertIsNotNone(
            result_type,
            f"review snapshot module lacks typed result {name}",
        )
        if result_type is None:
            self.fail(f"review snapshot module lacks typed result {name}")
        self.assertIs(type, type(result_type))
        return result_type

    def _assert_bundle_integrity_result(
        self,
        result: Any,
        snapshot: dict[str, Any],
    ) -> None:
        result_type = self._required_result_type(
            "BundleIntegrityResult"
        )
        self.assertIsInstance(result, result_type)
        self.assertEqual(
            snapshot["snapshot_content_id"],
            result.snapshot_content_id,
        )
        self.assertIs(True, result.integrity_valid)
        self.assertEqual(
            "UNVERIFIED",
            result.git_provenance_state,
        )
        self.assertEqual(
            "UNVERIFIED",
            result.live_verification_state,
        )
        self.assertEqual(
            "NOT_AUTHORIZED",
            result.authorization_state,
        )

    def _parse_receipt_utc(self, value: Any) -> datetime:
        self.assertIs(type(value), str)
        self.assertTrue(value.endswith("Z"))
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
        self.assertEqual(timezone.utc, parsed.tzinfo)
        return parsed

    def _assert_live_receipt(
        self,
        receipt: Any,
        *,
        boundary: str,
        snapshot: dict[str, Any],
        repository: TemporaryGitRepository,
        call_started: datetime,
        call_completed: datetime,
    ) -> None:
        receipt_type = self._required_result_type(
            "LiveVerificationReceipt"
        )
        self.assertIsInstance(receipt, receipt_type)
        self.assertEqual(boundary, receipt.boundary)
        self.assertEqual(
            snapshot["snapshot_content_id"],
            receipt.snapshot_content_id,
        )
        started = self._parse_receipt_utc(
            receipt.verification_started_at_utc
        )
        completed = self._parse_receipt_utc(
            receipt.verification_completed_at_utc
        )
        clock_slack = timedelta(seconds=2)
        self.assertLessEqual(call_started - clock_slack, started)
        self.assertLessEqual(started, completed)
        self.assertLessEqual(completed, call_completed + clock_slack)

        identity = receipt.repository_root_identity
        self.assertIs(type(identity), dict)
        root_stat = repository.root.stat()
        self.assertEqual(
            str(repository.root.resolve()),
            identity["resolved_path"],
        )
        self.assertEqual(root_stat.st_dev, identity["st_dev"])
        self.assertEqual(root_stat.st_ino, identity["st_ino"])
        self.assertIs(False, receipt.continuous_observation)
        self.assertEqual("UNVERIFIED", receipt.authority_state)
        self.assertEqual("UNVERIFIED", receipt.persistence_state)
        self.assertEqual(
            "NOT_AUTHORIZED",
            receipt.authorization_state,
        )

    def test_reviewer_readable_bundle_excludes_non_allowlisted_git_bytes(
        self,
    ) -> None:
        repository = self._new_repository()
        outside_path = "outside-review-history.md"
        outside_baseline = b"OUTSIDE-BASELINE-MARKER-4c6840\n"
        repository.write(outside_path, outside_baseline)
        run_git(repository.root, "add", "--", outside_path)
        run_git(repository.root, "commit", "-m", "add outside baseline")
        outside_index_marker = b"OUTSIDE-INDEX-MARKER-8c4242\n"
        repository.write(outside_path, outside_index_marker)
        run_git(repository.root, "add", "--", outside_path)
        outside_worktree_marker = b"OUTSIDE-WORKTREE-MARKER-a731d9\n"
        repository.write(outside_path, outside_worktree_marker)
        snapshot = self._build(repository)

        with tempfile.TemporaryDirectory() as directory:
            bundle_path = write_snapshot_bundle(
                snapshot,
                repository.root,
                Path(directory).resolve(),
            )
            leaked_files: list[str] = []
            forbidden_preimages = (
                outside_path.encode("ascii"),
                outside_baseline.rstrip(b"\n"),
                outside_index_marker.rstrip(b"\n"),
                outside_worktree_marker.rstrip(b"\n"),
            )
            for candidate in bundle_path.rglob("*"):
                if not candidate.is_file():
                    continue
                raw = candidate.read_bytes()
                if any(
                    forbidden in raw
                    for forbidden in forbidden_preimages
                ):
                    leaked_files.append(
                        candidate.relative_to(bundle_path).as_posix()
                    )
            self.assertEqual(
                [],
                leaked_files,
                "reviewer-readable bundle exposes non-allowlisted Git bytes",
            )

    def test_ready_status_in_non_machine_markdown_context_is_rejected(
        self,
    ) -> None:
        repository = self._new_repository()
        candidates = {
            "fenced example": (
                b"# Plan\n\nLifecycle: `IN_PROGRESS`\n\n"
                b"```text\n"
                b"Status: `READY_FOR_FINAL_REVIEW`\n"
                b"```\n"
            ),
            "HTML comment": (
                b"# Plan\n\nLifecycle: `IN_PROGRESS`\n\n"
                b"<!--\n"
                b"Status: `READY_FOR_FINAL_REVIEW`\n"
                b"-->\n"
            ),
            "narrative example": (
                b"# Plan\n\nLifecycle: `IN_PROGRESS`\n\n"
                b"## Example\n\n"
                b"Status: `READY_FOR_FINAL_REVIEW`\n"
            ),
        }
        for label, raw in candidates.items():
            with self.subTest(label=label):
                repository.write(REVIEW_SUBJECT_PATH, raw)
                with self.assertRaises(ReviewSnapshotError):
                    build_snapshot(
                        repository.root,
                        (REVIEW_SUBJECT_PATH,),
                        snapshot_instance_id=SNAPSHOT_INSTANCE_ID,
                        capture_started_at_utc=CAPTURE_STARTED_AT_UTC,
                        capture_completed_at_utc=(
                            CAPTURE_COMPLETED_AT_UTC
                        ),
                        required_focus_areas=REQUIRED_FOCUS_AREAS,
                        review_subject_path=REVIEW_SUBJECT_PATH,
                    )

    def test_git_index_environment_is_rejected_or_ignored(self) -> None:
        clean_environment = self._clean_git_environment()
        with mock.patch.dict(
            os.environ,
            clean_environment,
            clear=True,
        ):
            repository = self._new_repository()
            baseline = self._build(repository)
            with tempfile.TemporaryDirectory() as directory:
                alternate_index = Path(directory) / "alternate.index"
                alternate_environment = {
                    **clean_environment,
                    "GIT_INDEX_FILE": str(alternate_index),
                }
                result = subprocess.run(
                    ["git", "read-tree", "HEAD"],
                    cwd=repository.root,
                    env=alternate_environment,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    shell=False,
                    check=False,
                )
                self.assertEqual(0, result.returncode, result.stderr)
                self._assert_git_environment_rejected_or_ignored(
                    repository,
                    baseline,
                    clean_environment,
                    {
                        "GIT_INDEX_FILE": str(alternate_index),
                    },
                )

    def test_git_dir_and_work_tree_environment_is_rejected_or_ignored(
        self,
    ) -> None:
        clean_environment = self._clean_git_environment()
        with mock.patch.dict(
            os.environ,
            clean_environment,
            clear=True,
        ):
            repository = self._new_repository()
            alternate = self._new_repository()
            alternate.write("alternate-head.txt", b"alternate\n")
            run_git(alternate.root, "add", "--", "alternate-head.txt")
            run_git(alternate.root, "commit", "-m", "alternate head")
            baseline = self._build(repository)
            cases = {
                "GIT_DIR": {
                    "GIT_DIR": str(alternate.root / ".git"),
                },
                "GIT_DIR and GIT_WORK_TREE": {
                    "GIT_DIR": str(alternate.root / ".git"),
                    "GIT_WORK_TREE": str(repository.root),
                },
                "GIT_WORK_TREE": {
                    "GIT_WORK_TREE": str(alternate.root),
                },
            }
            for label, contamination in cases.items():
                with self.subTest(label=label):
                    self._assert_git_environment_rejected_or_ignored(
                        repository,
                        baseline,
                        clean_environment,
                        contamination,
                    )

    def test_git_object_directory_environment_is_rejected_or_ignored(
        self,
    ) -> None:
        clean_environment = self._clean_git_environment()
        with mock.patch.dict(
            os.environ,
            clean_environment,
            clear=True,
        ):
            repository = self._new_repository()
            alternate = self._new_repository()
            baseline = self._build(repository)
            self._assert_git_environment_rejected_or_ignored(
                repository,
                baseline,
                clean_environment,
                {
                    "GIT_OBJECT_DIRECTORY": str(
                        alternate.root / ".git" / "objects"
                    ),
                },
            )

    def test_git_config_environment_is_rejected_or_ignored(self) -> None:
        clean_environment = self._clean_git_environment()
        with mock.patch.dict(
            os.environ,
            clean_environment,
            clear=True,
        ):
            repository = self._new_repository()
            baseline = self._build(repository)
            with tempfile.TemporaryDirectory() as directory:
                injected_config = Path(directory) / "injected.gitconfig"
                injected_config.write_bytes(
                    b"[diff]\n\tnoprefix = true\n"
                )
                cases = {
                    "counted parameters": {
                        "GIT_CONFIG_COUNT": "1",
                        "GIT_CONFIG_KEY_0": "diff.noprefix",
                        "GIT_CONFIG_VALUE_0": "true",
                    },
                    "global config": {
                        "GIT_CONFIG_GLOBAL": str(injected_config),
                    },
                    "system config": {
                        "GIT_CONFIG_SYSTEM": str(injected_config),
                    },
                    "disable system config": {
                        "GIT_CONFIG_NOSYSTEM": "1",
                    },
                }
                for label, contamination in cases.items():
                    with self.subTest(label=label):
                        self._assert_git_environment_rejected_or_ignored(
                            repository,
                            baseline,
                            clean_environment,
                            contamination,
                        )

    def test_offline_api_requires_expected_snapshot_content_id(
        self,
    ) -> None:
        self._required_result_type("BundleIntegrityResult")
        self._required_keyword_only_parameter(
            verify_snapshot_bundle,
            "expected_snapshot_content_id",
        )

    def test_offline_result_is_typed_and_explicitly_non_authorizing(
        self,
    ) -> None:
        self._required_result_type("BundleIntegrityResult")
        self._required_keyword_only_parameter(
            verify_snapshot_bundle,
            "expected_snapshot_content_id",
        )
        repository = self._new_repository()
        snapshot = self._build(repository)
        with tempfile.TemporaryDirectory() as directory:
            bundle_path = write_snapshot_bundle(
                snapshot,
                repository.root,
                Path(directory).resolve(),
            )
            result = verify_snapshot_bundle(
                bundle_path,
                expected_snapshot_content_id=(
                    snapshot["snapshot_content_id"]
                ),
            )
            self._assert_bundle_integrity_result(result, snapshot)

    def test_resigned_bundle_is_rejected_by_out_of_band_expected_id(
        self,
    ) -> None:
        self._required_keyword_only_parameter(
            verify_snapshot_bundle,
            "expected_snapshot_content_id",
        )
        repository = self._new_repository()
        snapshot = self._build(repository)
        expected_content_id = snapshot["snapshot_content_id"]
        with tempfile.TemporaryDirectory() as directory:
            bundle_path = write_snapshot_bundle(
                snapshot,
                repository.root,
                Path(directory).resolve(),
            )
            resigned = copy.deepcopy(snapshot)
            resigned["capture_completed_at_utc"] = (
                "2026-07-29T01:02:05Z"
            )
            resign_snapshot(resigned)
            (bundle_path / "manifest.json").write_bytes(
                rfc8785.dumps(resigned) + b"\n"
            )
            with self.assertRaises(ReviewSnapshotError):
                verify_snapshot_bundle(
                    bundle_path,
                    expected_snapshot_content_id=expected_content_id,
                )

    def test_live_verification_returns_explicit_start_and_end_receipts(
        self,
    ) -> None:
        self._required_result_type("LiveVerificationReceipt")
        self._required_keyword_only_parameter(
            verify_snapshot,
            "boundary",
        )
        repository = self._new_repository()
        snapshot = self._build(repository)
        for boundary in ("REVIEW_START", "REVIEW_END"):
            with self.subTest(boundary=boundary):
                call_started = datetime.now(timezone.utc)
                receipt = verify_snapshot(
                    snapshot,
                    repository.root,
                    boundary=boundary,
                )
                call_completed = datetime.now(timezone.utc)
                self._assert_live_receipt(
                    receipt,
                    boundary=boundary,
                    snapshot=snapshot,
                    repository=repository,
                    call_started=call_started,
                    call_completed=call_completed,
                )

    def test_live_verification_rejects_unknown_boundary(self) -> None:
        self._required_keyword_only_parameter(
            verify_snapshot,
            "boundary",
        )
        repository = self._new_repository()
        snapshot = self._build(repository)
        with self.assertRaises(ReviewSnapshotError):
            verify_snapshot(
                snapshot,
                repository.root,
                boundary="DURING_REVIEW",
            )

    def test_offline_integrity_result_cannot_be_a_live_receipt(
        self,
    ) -> None:
        bundle_result_type = self._required_result_type(
            "BundleIntegrityResult"
        )
        live_receipt_type = self._required_result_type(
            "LiveVerificationReceipt"
        )
        self._required_keyword_only_parameter(
            verify_snapshot_bundle,
            "expected_snapshot_content_id",
        )
        repository = self._new_repository()
        snapshot = self._build(repository)
        with tempfile.TemporaryDirectory() as directory:
            bundle_path = write_snapshot_bundle(
                snapshot,
                repository.root,
                Path(directory).resolve(),
            )
            result = verify_snapshot_bundle(
                bundle_path,
                expected_snapshot_content_id=(
                    snapshot["snapshot_content_id"]
                ),
            )
            self.assertIsInstance(result, bundle_result_type)
            self.assertNotIsInstance(result, live_receipt_type)
            self.assertEqual(
                "UNVERIFIED",
                result.live_verification_state,
            )
            self.assertEqual(
                "NOT_AUTHORIZED",
                result.authorization_state,
            )

    def test_ancestor_link_exchange_fails_closed(self) -> None:
        repository = self._new_repository()
        inside_raw = (
            b"# Inside plan\n\n"
            b"Status: `READY_FOR_FINAL_REVIEW`\n"
        )
        outside_raw = (
            b"# Outside plan\n\n"
            b"Status: `READY_FOR_FINAL_REVIEW`\n"
        )
        repository.write(REVIEW_SUBJECT_PATH, inside_raw)
        repository_docs = repository.root / "docs"
        held_docs = repository.root / "docs-held"
        review_leaf = repository_docs / Path(REVIEW_SUBJECT_PATH).name

        with tempfile.TemporaryDirectory() as directory:
            outside_docs = Path(directory) / "outside-docs"
            outside_docs.mkdir()
            (outside_docs / review_leaf.name).write_bytes(outside_raw)
            real_lstat = Path.lstat
            link_active = False
            exchange_triggered = False
            leaf_observations = 0

            def create_directory_link() -> None:
                if os.name == "nt":
                    result = subprocess.run(
                        [
                            "cmd.exe",
                            "/c",
                            "mklink",
                            "/J",
                            str(repository_docs),
                            str(outside_docs),
                        ],
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        shell=False,
                        check=False,
                    )
                    self.assertEqual(
                        0,
                        result.returncode,
                        result.stderr.decode("utf-8", "replace"),
                    )
                elif os.name == "posix":
                    os.symlink(
                        outside_docs,
                        repository_docs,
                        target_is_directory=True,
                    )
                else:
                    self.fail(
                        "platform lacks a certified ancestor-link test"
                    )

            def remove_directory_link() -> None:
                if os.name == "nt":
                    os.rmdir(repository_docs)
                else:
                    repository_docs.unlink()

            def exchange_on_lstat(path: Path) -> os.stat_result:
                nonlocal exchange_triggered, link_active, leaf_observations
                observed = real_lstat(path)
                if path == repository_docs and not link_active:
                    os.rename(repository_docs, held_docs)
                    create_directory_link()
                    exchange_triggered = True
                    link_active = True
                elif path == review_leaf and link_active:
                    leaf_observations += 1
                    if leaf_observations % 2 == 0:
                        remove_directory_link()
                        os.rename(held_docs, repository_docs)
                        link_active = False
                return observed

            capture_error: ReviewSnapshotError | None = None
            captured_snapshot: dict[str, Any] | None = None
            try:
                with mock.patch.object(
                    Path,
                    "lstat",
                    side_effect=exchange_on_lstat,
                    autospec=True,
                ):
                    try:
                        captured_snapshot = build_snapshot(
                            repository.root,
                            (REVIEW_SUBJECT_PATH,),
                            snapshot_instance_id=SNAPSHOT_INSTANCE_ID,
                            capture_started_at_utc=(
                                CAPTURE_STARTED_AT_UTC
                            ),
                            capture_completed_at_utc=(
                                CAPTURE_COMPLETED_AT_UTC
                            ),
                            required_focus_areas=REQUIRED_FOCUS_AREAS,
                            review_subject_path=REVIEW_SUBJECT_PATH,
                        )
                    except ReviewSnapshotError as exc:
                        capture_error = exc
            finally:
                if link_active:
                    remove_directory_link()
                if held_docs.exists() and not repository_docs.exists():
                    os.rename(held_docs, repository_docs)

            self.assertTrue(
                exchange_triggered,
                "ancestor link exchange was not exercised",
            )
            self.assertFalse(
                held_docs.exists(),
                "held repository directory was not restored",
            )
            self.assertEqual(inside_raw, review_leaf.read_bytes())

            if capture_error is not None:
                return

            self.assertIsNotNone(captured_snapshot)
            if captured_snapshot is None:
                self.fail("capture returned neither a snapshot nor an error")
            subject_records = [
                entry
                for entry in captured_snapshot["files"]
                if entry["repository_path"] == REVIEW_SUBJECT_PATH
            ]
            self.assertEqual(1, len(subject_records))
            subject_record = subject_records[0]
            self.assertNotEqual(
                sha256_id(outside_raw),
                subject_record["sha256"],
            )
            self.assertNotEqual(
                len(outside_raw),
                subject_record["byte_size"],
            )
            self.assertEqual(
                sha256_id(inside_raw),
                subject_record["sha256"],
            )
            self.assertEqual(
                len(inside_raw),
                subject_record["byte_size"],
            )


if __name__ == "__main__":
    unittest.main()
