"""Tool and shell command policy for Execution Subgraph v2."""

from __future__ import annotations

from pathlib import Path

from aegis.modules.execution.models import CommandSafetyAnalysis


def analyze_shell_command(
    command_id: str,
    command: str,
    *,
    cwd: str,
    project_root: str | None = None,
    allowed_by_approved_plan: bool = False,
) -> CommandSafetyAnalysis:
    """Classify shell command risk from the command string and cwd."""

    lowered = command.lower().strip()
    risk = "unknown"
    network_expected = False
    if lowered.startswith("git push") or "gh pr" in lowered or " deploy" in lowered:
        risk = "remote_publish"
        network_expected = True
    elif any(token in lowered for token in ["rm -rf", "remove-item -recurse", "git reset --hard"]):
        risk = "destructive"
    elif any(token in lowered for token in ["pytest", "ruff", "python -m pytest"]):
        risk = "read_only"
    elif any(token in lowered for token in ["pip install", "curl ", "invoke-webrequest"]):
        risk = "external_write"
        network_expected = True

    cwd_path = Path(cwd).resolve()
    if project_root is not None:
        root = Path(project_root).resolve()
        if cwd_path != root and root not in cwd_path.parents:
            risk = "unknown"

    return CommandSafetyAnalysis(
        command_id=command_id,
        command=command,
        cwd=str(cwd_path),
        parsed_risk=risk,
        touches_paths=[],
        network_access_expected=network_expected,
        requires_interrupt=risk in {"unknown", "destructive", "external_write", "remote_publish"},
        allowed_by_approved_plan=allowed_by_approved_plan,
    )
