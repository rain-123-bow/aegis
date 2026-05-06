from __future__ import annotations

import argparse
import json
from pathlib import Path

from .leader import FinalReviewLeader


def run_demo(request_path: Path, output_dir: Path | None = None) -> dict:
    request = json.loads(request_path.read_text(encoding="utf-8"))
    leader = FinalReviewLeader(output_dir)
    result = leader.run(request)
    return result.to_dict()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Aegis Final Review Department demo runtime.")
    parser.add_argument("--request", required=True, help="Path to a Final Review request JSON file.")
    parser.add_argument("--output-dir", default=None, help="Optional private runtime output directory.")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_arg_parser().parse_args(argv)
    result = run_demo(Path(args.request), Path(args.output_dir) if args.output_dir else None)
    print(
        json.dumps(
            {
                "final_review_result_id": result["final_review_result_id"],
                "decision": result["decision"],
                "target": result["target"],
                "resource_policy_status": result["resource_policy"]["status"],
                "recommended_master_action": result["recommended_master_action"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
