from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from .canonical import load_json, verify_self_hash
from .generator import validated_domain_order


def load_manifest(path: str | Path) -> dict[str, Any]:
    manifest = load_json(path)
    if not isinstance(manifest, dict):
        raise ValueError("evaluation manifest must be a JSON object")
    suites = manifest.get("property_suites")
    if not isinstance(suites, list):
        raise ValueError("evaluation manifest property_suites must be an array")
    suite_ids: set[str] = set()
    for suite in suites:
        _validate_property_suite(suite)
        suite_id = suite["suite_id"]
        if suite_id in suite_ids:
            raise ValueError(f"duplicate property suite: {suite_id}")
        suite_ids.add(suite_id)
    return manifest


def property_suite(
    manifest: dict[str, Any], suite_id: str
) -> dict[str, Any]:
    matches = [
        suite
        for suite in manifest["property_suites"]
        if suite.get("suite_id") == suite_id
    ]
    if len(matches) != 1:
        raise KeyError(
            f"expected exactly one property suite {suite_id!r}; found {len(matches)}"
        )
    return matches[0]


def _validate_property_suite(suite: Any) -> None:
    if not isinstance(suite, dict):
        raise ValueError("property suite must be an object")
    suite_id = suite.get("suite_id")
    if not isinstance(suite_id, str) or not suite_id:
        raise ValueError("property suite requires suite_id")
    domain = suite.get("domain")
    if not isinstance(domain, dict) or not domain:
        raise ValueError(f"{suite_id}: domain must be a non-empty object")
    try:
        domain_order = validated_domain_order(suite)
    except ValueError as error:
        raise ValueError(f"{suite_id}: {error}") from error
    expected = suite.get("expected_instance_count")
    calculated = math.prod(len(domain[name]) for name in domain_order)
    if expected != calculated:
        raise ValueError(
            f"{suite_id}: expected_instance_count={expected}, calculated={calculated}"
        )


def verify_bidirectional_bindings(
    source_manifest: dict[str, Any],
    evaluation_manifest: dict[str, Any],
) -> dict[str, Any]:
    """Audit every declared algorithm hash in both directions."""

    entries = source_manifest.get("algorithm_entries", [])
    entry_by_id = {
        entry.get("entry_id"): entry
        for entry in entries
        if isinstance(entry, dict)
    }
    referenced: dict[str, set[str]] = {}
    hash_mismatch_ids: set[str] = set()
    missing_entry_ids: set[str] = set()

    def bind(entry_id: Any, declared_hash: Any, source: str) -> None:
        if not isinstance(entry_id, str):
            return
        referenced.setdefault(entry_id, set()).add(source)
        entry = entry_by_id.get(entry_id)
        if entry is None:
            missing_entry_ids.add(entry_id)
            return
        if (
            not verify_self_hash(entry, "entry_sha256")
            or entry.get("entry_sha256") != declared_hash
        ):
            hash_mismatch_ids.add(entry_id)

    for suite in evaluation_manifest.get("property_suites", []):
        suite_id = str(suite.get("suite_id", "<unknown-suite>"))
        for field in (
            "generator",
            "input_materializer",
            "reference_oracle",
        ):
            binding = suite.get(field)
            if not isinstance(binding, dict):
                continue
            bind(
                binding.get("algorithm_id"),
                binding.get("source_manifest_entry_sha256"),
                f"property_suites/{suite_id}/{field}",
            )

    for spec in source_manifest.get("comparator_specs", []):
        comparator_id = str(spec.get("comparator_id", "<unknown-comparator>"))
        bind(
            spec.get("algorithm_entry_id"),
            spec.get("algorithm_entry_sha256"),
            f"comparator_specs/{comparator_id}/decision",
        )
        trace_id = spec.get("trace_algorithm_entry_id")
        if trace_id is not None:
            bind(
                trace_id,
                spec.get("trace_algorithm_entry_sha256"),
                f"comparator_specs/{comparator_id}/trace",
            )

    executable_entry_ids = {
        entry_id
        for entry_id in entry_by_id
        if isinstance(entry_id, str)
        and entry_id != "REFERENCE-CLI-JSONL-V1"
    }
    unreferenced = executable_entry_ids - set(referenced)
    return {
        "schema_version": "ReferenceBindingAudit.v1",
        "valid": not (
            missing_entry_ids or hash_mismatch_ids or unreferenced
        ),
        "referenced_entry_ids": sorted(referenced),
        "unreferenced_entry_ids": sorted(unreferenced),
        "missing_entry_ids": sorted(missing_entry_ids),
        "hash_mismatch_ids": sorted(hash_mismatch_ids),
        "reference_sites": {
            entry_id: sorted(sites)
            for entry_id, sites in sorted(referenced.items())
        },
    }
