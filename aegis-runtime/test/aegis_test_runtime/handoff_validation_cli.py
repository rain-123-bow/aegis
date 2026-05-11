from __future__ import annotations

import argparse
import json
import os
import shlex
from pathlib import Path
from typing import Any

from .handoff_validation import run_test_handoff_validation


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Phase 20A Test handoff validation.")
    parser.add_argument("--handoff", required=True, help="Path to Execution handoff package JSON.")
    parser.add_argument("--output-dir", required=True, help="Directory for Phase 20A validation outputs.")
    parser.add_argument("--test-command", action="append", help="Test command to run. Supply once as a shell-like string.")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_arg_parser().parse_args(argv)
    handoff = _read_json(args.handoff)
    command = None
    if args.test_command:
        if len(args.test_command) != 1:
            raise SystemExit("Phase 20A currently accepts exactly one --test-command")
        command = shlex.split(args.test_command[0], posix=os.name != "nt")
    report = run_test_handoff_validation(handoff, output_dir=args.output_dir, default_test_command=command)
    print(json.dumps({
        "status": report["status"],
        "test_result": report["test_result"],
        "run_id": report["run_id"],
        "integration_branch": report["integration_branch"],
        "integration_commit": report["integration_commit"],
        "output_dir": str(Path(args.output_dir)),
    }, ensure_ascii=False, indent=2, sort_keys=True))


def _read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
