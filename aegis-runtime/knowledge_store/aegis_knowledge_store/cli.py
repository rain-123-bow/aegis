from __future__ import annotations

import argparse
import json
from pathlib import Path

from .persistence import persist_knowledge_candidate_file


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Aegis Phase 23B local Knowledge Store persistence.")
    sub = parser.add_subparsers(dest="command", required=True)

    persist = sub.add_parser("persist", help="Persist one knowledge_candidate JSON file.")
    persist.add_argument("--knowledge-candidate", required=True, help="Path to knowledge candidate JSON.")
    persist.add_argument("--knowledge-root", required=True, help="Target local knowledge/ root directory.")
    persist.add_argument("--output", help="Optional output path for knowledge persistence result JSON.")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_arg_parser().parse_args(argv)
    if args.command == "persist":
        result = persist_knowledge_candidate_file(
            args.knowledge_candidate,
            knowledge_root=args.knowledge_root,
        ).to_dict()
        if args.output:
            output = Path(args.output)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return
    raise SystemExit(f"unknown command: {args.command}")


if __name__ == "__main__":
    main()
