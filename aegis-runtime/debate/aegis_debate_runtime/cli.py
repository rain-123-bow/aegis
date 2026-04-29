from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .leader import DebateLeaderRuntime


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Aegis Debate Department demo runtime.")
    parser.add_argument("--request", required=True, help="Path to a debate request JSON file.")
    parser.add_argument("--output", help="Optional path to write the final run result JSON.")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_arg_parser().parse_args(argv)
    request_path = Path(args.request)
    data: dict[str, Any] = json.loads(request_path.read_text(encoding="utf-8"))
    result = DebateLeaderRuntime().run(data).to_dict()
    final_report = result["final_report"]
    selected_position = final_report.get("selected_position") or {}
    result["selected_stance"] = selected_position.get("stance_id")
    result["decision"] = final_report.get("decision")
    result["final_report_path"] = str(Path(args.output).resolve()) if args.output else None
    text = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)


if __name__ == "__main__":
    main()
