"""Command safety analysis for Test Subgraph v2."""

from __future__ import annotations

from pathlib import Path

from aegis.modules.test.models import ArtifactRef, TestCommandSafetyAnalysis, TestWritePolicy


def analyze_test_command(
    *,
    test_id: str,
    command: str,
    cwd: str | Path,
    write_policy: TestWritePolicy,
    write_policy_ref: ArtifactRef,
) -> TestCommandSafetyAnalysis:
    """Classify a deterministic test command before execution."""

    cwd_path = Path(cwd).resolve()
    command_lc = command.lower()
    touches: list[str] = []
    parsed_risk = "read_only"
    reason = None
    blocked = False
    requires_interrupt = False

    if "git push" in command_lc or "gh pr create" in command_lc:
        parsed_risk = "remote_publish"
        blocked = True
        requires_interrupt = True
        reason = "remote publication is forbidden in Test Subgraph"
    elif "rm -rf" in command_lc or "remove-item" in command_lc:
        parsed_risk = "destructive"
        blocked = True
        requires_interrupt = True
        reason = "destructive command is forbidden in Test Subgraph"
    elif command_lc.startswith("curl ") or command_lc.startswith("Invoke-WebRequest".lower()):
        parsed_risk = "external_write"
        blocked = True
        requires_interrupt = True
        reason = "external write/network command is not allowed by deterministic Test runtime"
    elif command.startswith("aegis:write_code "):
        parsed_risk = "test_write"
        code_target = Path(write_policy.forbidden_roots[0]) / command.removeprefix(
            "aegis:write_code "
        ).strip()
        touches.append(str(code_target.resolve()))
        blocked = True
        reason = "command targets a forbidden root"
    elif not command.startswith("aegis:"):
        parsed_risk = "unknown"
        blocked = True
        requires_interrupt = True
        reason = "unknown command cannot be executed by deterministic Test runtime"

    forbidden_roots = [Path(root).resolve() for root in write_policy.forbidden_roots]
    forbidden_touched = [
        path
        for path in touches
        if any(Path(path).resolve() == root or root in Path(path).resolve().parents for root in forbidden_roots)
    ]
    if forbidden_touched:
        blocked = True
        reason = reason or "command touches forbidden root"

    allowed_roots = [write_policy.test_run_dir, *write_policy.allowed_temp_roots]
    return TestCommandSafetyAnalysis(
        test_id=test_id,
        command=command,
        cwd=str(cwd_path),
        write_policy_ref=write_policy_ref,
        parsed_risk=parsed_risk,  # type: ignore[arg-type]
        touches_paths=touches,
        allowed_write_roots=allowed_roots,
        forbidden_roots_touched=forbidden_touched,
        requires_interrupt=requires_interrupt,
        blocked=blocked,
        reason=reason,
    )
