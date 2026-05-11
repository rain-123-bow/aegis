from __future__ import annotations

import argparse
import json
from pathlib import Path

from .phase21a_handoff import run_phase21a_handoff_validation


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Aegis Final Review Phase 21A handoff validation.")
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="Validate a Test Phase 20B handoff package.")
    run_parser.add_argument("--handoff-package", required=True, help="Path to the Test Phase 20B Final Review handoff JSON.")
    run_parser.add_argument("--output-dir", required=True, help="Directory for Phase 21A validation artifacts.")

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    if args.command != "run":
        parser.error("a subcommand is required: run")

    summary = run_phase21a_handoff_validation(
        handoff_package_path=Path(args.handoff_package),
        output_dir=Path(args.output_dir),
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
