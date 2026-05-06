from __future__ import annotations

import argparse
import json
from pathlib import Path

from .leader import TestLeader


def run_demo(request_path: Path, output_dir: Path | None = None) -> dict:
    request = json.loads(request_path.read_text(encoding="utf-8"))
    leader = TestLeader(output_dir)
    report = leader.run(request)
    return report.to_dict()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Aegis Test Department demo runtime.")
    parser.add_argument("--request", required=True, help="Path to a Test request JSON file.")
    parser.add_argument("--output-dir", default=None, help="Optional private runtime output directory.")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_arg_parser().parse_args(argv)
    result = run_demo(Path(args.request), Path(args.output_dir) if args.output_dir else None)
    print(
        json.dumps(
            {
                "run_id": result["run_id"],
                "result": result["result"],
                "feedback_kind": result["feedback_kind"],
                "next_route": result["next_route"],
                "final_report_path": result["artifact_paths"]["final_report"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
