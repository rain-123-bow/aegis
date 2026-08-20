from __future__ import annotations

import itertools
import math
from collections.abc import Iterator
from typing import Any

from .canonical import content_id, jcs_bytes, with_self_hash


PROPERTY_ENVELOPE_SCHEMA_VERSION = "PropertyInstanceEnvelope.v1"


def count_instances(suite: dict[str, Any]) -> int:
    names = validated_domain_order(suite)
    return math.prod(len(suite["domain"][name]) for name in names)


def validated_domain_order(suite: dict[str, Any]) -> tuple[str, ...]:
    """Validate and return the sole normative property enumeration order."""

    domain = suite.get("domain")
    domain_order = suite.get("domain_order")
    if not isinstance(domain, dict) or not domain:
        raise ValueError("suite domain must be a non-empty object")
    if not all(isinstance(name, str) and name for name in domain):
        raise ValueError("domain field names must be non-empty strings")
    if (
        not isinstance(domain_order, list)
        or not domain_order
        or not all(isinstance(name, str) and name for name in domain_order)
    ):
        raise ValueError(
            "domain_order must be a non-empty array of field names"
        )
    if len(domain_order) != len(set(domain_order)):
        raise ValueError("domain_order contains duplicate field names")
    if set(domain_order) != set(domain):
        missing = sorted(set(domain) - set(domain_order))
        extra = sorted(set(domain_order) - set(domain))
        raise ValueError(
            "domain_order must contain each domain field exactly once; "
            f"missing={missing}, extra={extra}"
        )
    for name in domain_order:
        values = domain[name]
        if not isinstance(values, list) or not values:
            raise ValueError(f"domain {name!r} must be a non-empty array")
        canonical_values = [jcs_bytes(value) for value in values]
        if len(canonical_values) != len(set(canonical_values)):
            raise ValueError(f"domain {name!r} contains a JCS-duplicate value")
        if not all(isinstance(value, str) and value for value in values):
            raise ValueError(
                f"domain {name!r} values must be non-empty strings"
            )
    return tuple(domain_order)


def iter_assignments(suite: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Yield the Cartesian product in explicit domain and value-array order."""

    names = validated_domain_order(suite)
    value_arrays = tuple(suite["domain"][name] for name in names)
    for values in itertools.product(*value_arrays):
        yield dict(zip(names, values, strict=True))


def instance_id(suite_id: str, assignment: dict[str, Any]) -> str:
    """Implement sha256:JCS({suite_id, lexicographically keyed assignment})."""

    return content_id({"suite_id": suite_id, "assignment": assignment})


def property_case_id(suite_id: str, ordinal: int) -> str:
    if ordinal < 1:
        raise ValueError("property ordinal must be one-based")
    return f"{suite_id}-INSTANCE-{ordinal:06d}"


def iter_property_envelopes(
    suite: dict[str, Any],
) -> Iterator[dict[str, Any]]:
    """Yield evaluator-only identities and assignments, never expectations."""

    suite_id = suite["suite_id"]
    seen_instance_ids: set[str] = set()
    for ordinal, assignment in enumerate(iter_assignments(suite), start=1):
        stable_id = instance_id(suite_id, assignment)
        if stable_id in seen_instance_ids:
            raise ValueError(
                f"duplicate property instance_id at ordinal {ordinal}: "
                f"{stable_id}"
            )
        seen_instance_ids.add(stable_id)
        envelope = {
            "schema_version": PROPERTY_ENVELOPE_SCHEMA_VERSION,
            "suite_id": suite_id,
            "ordinal": ordinal,
            "instance_id": stable_id,
            "case_id": property_case_id(suite_id, ordinal),
            "assignment": assignment,
        }
        yield with_self_hash(envelope, "envelope_sha256", prefix=True)
