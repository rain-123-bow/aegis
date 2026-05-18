from __future__ import annotations

import argparse
import json
from pathlib import Path

from .linkage import load_json_object, validate_three_store_linkage


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Aegis Phase 23C local three-store linkage validation.")
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate", help="Validate local Archive/Knowledge/Causal cross-store references.")
    validate.add_argument("--archive-root", required=True, help="Path to local archive/ root directory.")
    validate.add_argument("--knowledge-root", required=True, help="Path to local knowledge/ root directory.")
    validate.add_argument("--causal-root", required=True, help="Path to local causal/ root directory.")
    validate.add_argument("--linkage-request", help="Optional Master-verified linkage request JSON.")
    validate.add_argument("--output", help="Optional output path for linkage validation result JSON.")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_arg_parser().parse_args(argv)
    if args.command == "validate":
        request = load_json_object(args.linkage_request) if args.linkage_request else None
        result = validate_three_store_linkage(
            archive_root=args.archive_root,
            knowledge_root=args.knowledge_root,
            causal_root=args.causal_root,
            linkage_request=request,
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
