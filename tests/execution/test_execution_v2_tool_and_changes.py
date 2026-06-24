from __future__ import annotations

from pathlib import Path

from aegis.modules.execution.changeset import (
    diff_code_tree_snapshots,
    scan_code_tree,
    validate_implementation_changeset,
)
from aegis.modules.execution.models import (
    ArtifactRef,
    ChangedFile,
    ExpectedFileChange,
    ImplementationChangeSet,
)
from aegis.modules.execution.tool_policy import analyze_shell_command


def artifact_ref(kind: str = "test") -> ArtifactRef:
    return ArtifactRef(
        artifact_id=f"{kind}-artifact",
        artifact_type=kind,
        path=f"/tmp/{kind}",
        readme_path=f"/tmp/{kind}/README.md",
        sha256="0" * 64,
        created_by_node="unit_test",
    )


def test_changed_file_requires_expected_change_id() -> None:
    expected = ExpectedFileChange(
        change_id="chg-1",
        path="src/main.py",
        allowed_change_types=["modified"],
        requirement_refs=["REQ-1"],
        rationale="Update implementation.",
    )
    changeset = ImplementationChangeSet(
        run_id="run-1",
        approved_plan_ref=artifact_ref("plan"),
        expected_file_changes_ref=artifact_ref("expected"),
        before_tree_hash="a" * 64,
        after_tree_hash="b" * 64,
        changed_files=[
            ChangedFile(
                path="src/main.py",
                change_type="modified",
                within_code_root=True,
                expected_by_plan=False,
                sha256_before="c" * 64,
                sha256_after="d" * 64,
            )
        ],
    )

    validated = validate_implementation_changeset(changeset, [expected])

    assert validated.status == "accepted"
    assert validated.changed_files[0].expected_by_plan is True
    assert validated.changed_files[0].expected_change_id == "chg-1"


def test_unexpected_changed_file_blocks_changeset() -> None:
    expected = ExpectedFileChange(
        change_id="chg-1",
        path="src/main.py",
        allowed_change_types=["modified"],
        requirement_refs=["REQ-1"],
        rationale="Update implementation.",
    )
    changeset = ImplementationChangeSet(
        run_id="run-1",
        approved_plan_ref=artifact_ref("plan"),
        expected_file_changes_ref=artifact_ref("expected"),
        before_tree_hash="a" * 64,
        after_tree_hash="b" * 64,
        changed_files=[
            ChangedFile(
                path="src/other.py",
                change_type="modified",
                within_code_root=True,
                expected_by_plan=False,
                sha256_before="c" * 64,
                sha256_after="d" * 64,
            )
        ],
    )

    validated = validate_implementation_changeset(changeset, [expected])

    assert validated.status == "blocked"
    assert validated.unexpected_changes == ["src/other.py"]


def test_diff_scanner_detects_added_modified_deleted_files(tmp_path: Path) -> None:
    code_root = tmp_path / "code"
    code_root.mkdir()
    keep = code_root / "keep.txt"
    delete = code_root / "delete.txt"
    keep.write_text("before\n", encoding="utf-8", newline="\n")
    delete.write_text("remove\n", encoding="utf-8", newline="\n")
    before = scan_code_tree(code_root)

    keep.write_text("after\n", encoding="utf-8", newline="\n")
    delete.unlink()
    (code_root / "added.txt").write_text("new\n", encoding="utf-8", newline="\n")
    after = scan_code_tree(code_root)

    changed = diff_code_tree_snapshots(before, after)

    by_path = {item.path: item for item in changed}
    assert by_path["keep.txt"].change_type == "modified"
    assert by_path["keep.txt"].sha256_before is not None
    assert by_path["keep.txt"].sha256_after is not None
    assert by_path["delete.txt"].change_type == "deleted"
    assert by_path["delete.txt"].sha256_after is None
    assert by_path["added.txt"].change_type == "added"
    assert by_path["added.txt"].sha256_before is None


def test_shell_command_safety_classifies_remote_publish_and_destructive() -> None:
    push = analyze_shell_command("cmd-1", "git push", cwd="/repo")
    remove = analyze_shell_command("cmd-2", "rm -rf build", cwd="/repo")
    unknown = analyze_shell_command("cmd-3", "custom-tool --mutate", cwd="/repo")

    assert push.parsed_risk == "remote_publish"
    assert push.requires_interrupt is True
    assert remove.parsed_risk == "destructive"
    assert remove.requires_interrupt is True
    assert unknown.parsed_risk == "unknown"
    assert unknown.requires_interrupt is True
