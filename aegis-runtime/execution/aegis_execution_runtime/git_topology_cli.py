from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .git_topology import run_execution_git_topology_closure


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Execution Phase 19A local git topology closure.")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Run local git topology closure and emit Test handoff package.")
    run.add_argument("--request", required=True, help="Path to Phase 19A request JSON.")
    run.add_argument("--output-dir", required=True, help="Output directory for report and handoff package.")

    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_arg_parser().parse_args(argv)
    if args.command == "run":
        request = _read_json(args.request)
        report = run_execution_git_topology_closure(request, output_dir=args.output_dir)
        _print(
            {
                "run_id": report["run_id"],
                "status": report["status"],
                "integration_branch": report["integration_branch"],
                "integration_commit": report["integration_commit"],
                "group_count": len(report["group_records"]),
                "output_dir": str(Path(args.output_dir)),
            }
        )
        return
    raise SystemExit(f"unknown command: {args.command}")


def _read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _print(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
