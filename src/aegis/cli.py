from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from aegis.graph import AegisRuntime


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))


def run_command(args: argparse.Namespace) -> int:
    with AegisRuntime(Path(args.project_root)) as runtime:
        payload = runtime.run(goal=args.goal, thread_id=args.thread_id)
    _print_json(payload)
    return 0


def resume_command(args: argparse.Namespace) -> int:
    decision = json.loads(args.decision)
    with AegisRuntime(Path(args.project_root)) as runtime:
        payload = runtime.resume(thread_id=args.thread_id, decision=decision)
    _print_json(payload)
    return 0


def inspect_command(args: argparse.Namespace) -> int:
    with AegisRuntime(Path(args.project_root)) as runtime:
        payload = runtime.inspect(thread_id=args.thread_id)
    _print_json(payload)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aegis")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run")
    run.add_argument("--project-root", default=".")
    run.add_argument("--goal", required=True)
    run.add_argument("--thread-id")
    run.set_defaults(func=run_command)

    resume = subparsers.add_parser("resume")
    resume.add_argument("--project-root", default=".")
    resume.add_argument("--thread-id", required=True)
    resume.add_argument("--decision", required=True)
    resume.set_defaults(func=resume_command)

    inspect = subparsers.add_parser("inspect")
    inspect.add_argument("--project-root", default=".")
    inspect.add_argument("--thread-id", required=True)
    inspect.set_defaults(func=inspect_command)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

