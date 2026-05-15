from __future__ import annotations

import argparse
import json
from pathlib import Path

from .persistence import persist_archive_event_file


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Aegis Phase 23A local Archive segmented persistence.")
    sub = parser.add_subparsers(dest="command", required=True)

    persist = sub.add_parser("persist", help="Persist one archive_event_candidate JSON file.")
    persist.add_argument("--event-candidate", required=True, help="Path to archive event candidate JSON.")
    persist.add_argument("--archive-root", required=True, help="Target local archive/ root directory.")
    persist.add_argument("--max-events-per-segment", type=int, default=1000)
    persist.add_argument("--max-segment-size-bytes", type=int, default=5_000_000)
    persist.add_argument("--output", help="Optional output path for archive persistence result JSON.")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_arg_parser().parse_args(argv)
    if args.command == "persist":
        result = persist_archive_event_file(
            args.event_candidate,
            archive_root=args.archive_root,
            max_events_per_segment=args.max_events_per_segment,
            max_segment_size_bytes=args.max_segment_size_bytes,
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
