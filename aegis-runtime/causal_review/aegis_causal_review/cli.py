from __future__ import annotations

import argparse
import json
from pathlib import Path

from .validator import validate_review_file


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Aegis Phase 22B Master causal review validation.")
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate", help="Validate one Phase 22B causal review request JSON file.")
    validate.add_argument("--review-request", required=True, help="Path to causal review request JSON.")
    validate.add_argument("--output", help="Optional output path for causal_review_decision JSON.")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_arg_parser().parse_args(argv)
    if args.command == "validate":
        decision = validate_review_file(args.review_request).to_dict()
        if args.output:
            output = Path(args.output)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(decision, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(decision, ensure_ascii=False, indent=2, sort_keys=True))
        return
    raise SystemExit(f"unknown command: {args.command}")


if __name__ == "__main__":
    main()
