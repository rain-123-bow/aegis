from __future__ import annotations

import argparse
import base64
import binascii
import itertools
import sys
from collections.abc import Iterable
from typing import Any, BinaryIO

from .canonical import jsonl_bytes, load_json, loads_json
from .closure import (
    closure_sut_decision,
    evaluate_closure,
)
from .comparator import compare_outputs, compare_reference_traces
from .generator import iter_property_envelopes
from .manifest import load_manifest, property_suite
from .verdict import (
    evaluate_verdict_input,
    verdict_sut_decision,
)


def emit_jsonl(values: Iterable[Any], stream: BinaryIO) -> None:
    """Write canonical RFC 8785 JSONL with one write per record."""

    for value in values:
        stream.write(jsonl_bytes(value))
    stream.flush()


def _read_json_argument(path: str) -> Any:
    if path == "-":
        return loads_json(sys.stdin.buffer.read(), source="<stdin>")
    return load_json(path)


def _require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _decode_evidence_bytes(values: Any) -> dict[str, bytes]:
    if not isinstance(values, dict):
        raise ValueError("evidence_bytes_base64 must be an object")
    decoded: dict[str, bytes] = {}
    for evidence_id, encoded in values.items():
        if not isinstance(evidence_id, str) or not isinstance(encoded, str):
            raise ValueError(
                "evidence_bytes_base64 keys and values must be strings"
            )
        try:
            decoded[evidence_id] = base64.b64decode(
                encoded, validate=True
            )
        except (binascii.Error, ValueError) as exc:
            raise ValueError(
                f"invalid base64 evidence bytes for {evidence_id!r}"
            ) from exc
    return decoded


def _command_generate(args: argparse.Namespace) -> Iterable[Any]:
    manifest = load_manifest(args.manifest)
    suite = property_suite(manifest, args.suite_id)
    records = iter_property_envelopes(suite)
    if args.limit is None:
        return records
    if args.limit < 0:
        raise ValueError("--limit must be non-negative")
    return itertools.islice(records, args.limit)


def _command_verdict_assignment(
    args: argparse.Namespace,
) -> Iterable[Any]:
    assignment = _require_object(_read_json_argument(args.input), "input")
    return [verdict_sut_decision(assignment)]


def _command_verdict_input(args: argparse.Namespace) -> Iterable[Any]:
    subject = _require_object(_read_json_argument(args.input), "input")
    return [evaluate_verdict_input(subject)]


def _command_closure_assignment(
    args: argparse.Namespace,
) -> Iterable[Any]:
    assignment = _require_object(_read_json_argument(args.input), "input")
    return [closure_sut_decision(assignment)]


def _command_closure(args: argparse.Namespace) -> Iterable[Any]:
    envelope = _require_object(_read_json_argument(args.input), "input")
    evidence_records = _require_object(
        envelope.get("evidence_records"), "evidence_records"
    )
    return [
        evaluate_closure(
            _require_object(envelope.get("blocker"), "blocker"),
            _require_object(
                envelope.get("closure_event"), "closure_event"
            ),
            evidence_records,
            _decode_evidence_bytes(envelope.get("evidence_bytes_base64")),
            _require_object(
                envelope.get("dependency_propagation"),
                "dependency_propagation",
            ),
            schema_dir=args.schema_dir,
        )
    ]


def _command_compare_decision(
    args: argparse.Namespace,
) -> Iterable[Any]:
    expected = _require_object(
        _read_json_argument(args.expected), "expected"
    )
    actual = _require_object(_read_json_argument(args.actual), "actual")
    return [compare_outputs(expected, actual, args.schema_dir)]


def _command_compare_trace(args: argparse.Namespace) -> Iterable[Any]:
    expected = _read_json_argument(args.expected)
    actual = _read_json_argument(args.actual)
    return [
        compare_reference_traces(
            expected,
            actual,
            args.normalization,
            args.category,
        )
    ]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m evaluation.aegis_v2.reference"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate = subparsers.add_parser("generate")
    generate.add_argument("--manifest", required=True)
    generate.add_argument("--suite-id", required=True)
    generate.add_argument("--limit", type=int)
    generate.set_defaults(handler=_command_generate)

    verdict_assignment = subparsers.add_parser("verdict-assignment")
    verdict_assignment.add_argument("--input", default="-")
    verdict_assignment.set_defaults(handler=_command_verdict_assignment)

    verdict_input = subparsers.add_parser("verdict-input")
    verdict_input.add_argument("--input", default="-")
    verdict_input.set_defaults(handler=_command_verdict_input)

    closure_assignment = subparsers.add_parser("closure-assignment")
    closure_assignment.add_argument("--input", default="-")
    closure_assignment.set_defaults(handler=_command_closure_assignment)

    closure = subparsers.add_parser("closure")
    closure.add_argument("--input", default="-")
    closure.add_argument("--schema-dir", required=True)
    closure.set_defaults(handler=_command_closure)

    compare_decision = subparsers.add_parser("compare-decision")
    compare_decision.add_argument("--expected", required=True)
    compare_decision.add_argument("--actual", required=True)
    compare_decision.add_argument("--schema-dir", required=True)
    compare_decision.set_defaults(handler=_command_compare_decision)

    compare_trace = subparsers.add_parser("compare-trace")
    compare_trace.add_argument("--expected", required=True)
    compare_trace.add_argument("--actual", required=True)
    compare_trace.add_argument(
        "--normalization",
        choices=[
            "NONE",
            "DROP_OBSERVATION_TIME_ONLY_KEEP_ORDER_AND_IDENTITIES",
        ],
        required=True,
    )
    compare_trace.add_argument(
        "--category", choices=["RECOVERY", "SIDE_EFFECT"], required=True
    )
    compare_trace.set_defaults(handler=_command_compare_trace)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        values = args.handler(args)
        emit_jsonl(values, sys.stdout.buffer)
    except (OSError, TypeError, ValueError, KeyError) as exc:
        emit_jsonl(
            [
                {
                    "schema_version": "ReferenceCliError.v1",
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                }
            ],
            sys.stderr.buffer,
        )
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
