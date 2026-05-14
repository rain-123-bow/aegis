from __future__ import annotations

import argparse
import json
from pathlib import Path

from .persistence import persist_review_decision_file


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Aegis Phase 22C local Causal Store persistence.")
    sub = parser.add_subparsers(dest="command", required=True)

    persist = sub.add_parser("persist", help="Persist one Phase 22B causal review decision artifact.")
    persist.add_argument("--review-decision", required=True, help="Path to causal_review_decision JSON.")
    persist.add_argument("--causal-root", required=True, help="Target local causal/ root directory.")
    persist.add_argument("--output", help="Optional output path for persistence result JSON.")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_arg_parser().parse_args(argv)
    if args.command == "persist":
        result = persist_review_decision_file(args.review_decision, args.causal_root).to_dict()
        if args.output:
            output = Path(args.output)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return
    raise SystemExit(f"unknown command: {args.command}")


if __name__ == "__main__":
    main()
