from __future__ import annotations

import base64
import binascii
import copy
from pathlib import Path
from typing import Any

from .canonical import (
    jcs_bytes,
    loads_json,
    sha256_hex,
    sha256_hex_bytes,
    verify_self_hash,
    with_self_hash,
)
from .generator import (
    instance_id,
    property_case_id,
    validated_domain_order,
)
from .schema_validation import local_schema_bundle


PROPERTY_BUNDLE_SCHEMA_VERSION = "PropertyMaterializationBundle.v1"
SCHEMA_ID_BASE = (
    "https://raw.githubusercontent.com/rain-123-bow/"
    "aegis/main/schemas/aegis/v2/"
)
VERDICT_INPUT_SCHEMA_ID = f"{SCHEMA_ID_BASE}verdict_input.v1.schema.json"
BLOCKER_RECORD_SCHEMA_ID = (
    f"{SCHEMA_ID_BASE}blocker_record.v1.schema.json"
)


def validate_property_envelope(
    envelope: dict[str, Any],
    suite: dict[str, Any],
    *,
    schema_dir: str | Path,
) -> None:
    validator = local_schema_bundle(str(Path(schema_dir).resolve()))
    errors = validator.errors(
        envelope, "property_instance_envelope.v1.schema.json"
    )
    if errors:
        raise ValueError(f"property envelope schema invalid: {errors}")
    if not verify_self_hash(
        envelope, "envelope_sha256", prefix=True
    ):
        raise ValueError("property envelope self-hash mismatch")
    if envelope["suite_id"] != suite.get("suite_id"):
        raise ValueError("property envelope suite_id mismatch")
    assignment = envelope["assignment"]
    domain = suite.get("domain")
    try:
        domain_order = validated_domain_order(suite)
    except ValueError as error:
        raise ValueError(f"suite domain_order is invalid: {error}") from error
    if not isinstance(assignment, dict) or set(assignment) != set(domain_order):
        raise ValueError("property assignment field set mismatch")
    for name in domain_order:
        encoded = jcs_bytes(assignment[name])
        encoded_domain = [jcs_bytes(value) for value in domain[name]]
        if encoded not in encoded_domain:
            raise ValueError(
                f"property assignment value is outside domain: {name}"
            )
    calculated_ordinal = 1
    multiplier = 1
    for name in reversed(domain_order):
        encoded_domain = [jcs_bytes(value) for value in domain[name]]
        calculated_ordinal += encoded_domain.index(
            jcs_bytes(assignment[name])
        ) * multiplier
        multiplier *= len(encoded_domain)
    if envelope["ordinal"] != calculated_ordinal:
        raise ValueError("property envelope ordinal/assignment mismatch")
    stable_id = instance_id(envelope["suite_id"], assignment)
    if envelope["instance_id"] != stable_id:
        raise ValueError("property envelope instance_id mismatch")
    stable_case_id = property_case_id(
        envelope["suite_id"], envelope["ordinal"]
    )
    if envelope["case_id"] != stable_case_id:
        raise ValueError("property envelope case_id mismatch")


def make_materialized_json_fixture(
    *,
    fixture_id: str,
    logical_runtime_path: str,
    value: Any,
) -> dict[str, Any]:
    raw = jcs_bytes(value)
    raw_sha256 = sha256_hex_bytes(raw)
    return {
        "fixture_id": fixture_id,
        "logical_runtime_path": logical_runtime_path,
        "media_type": "application/json",
        "encoding": "UTF-8",
        "byte_domain": "INLINE_BASE64_DECODED_EXACT_BYTES",
        "raw_base64": base64.b64encode(raw).decode("ascii"),
        "byte_size": len(raw),
        "raw_sha256": raw_sha256,
        "jcs_sha256": sha256_hex(value),
        "content_id": f"sha256:{raw_sha256}",
        "access_mode": "READ_ONLY",
    }


def _validate_materialized_fixtures(
    fixtures: list[dict[str, Any]],
) -> None:
    fixture_ids: set[str] = set()
    runtime_paths: set[str] = set()
    for fixture in fixtures:
        fixture_id = fixture.get("fixture_id")
        runtime_path = fixture.get("logical_runtime_path")
        if fixture_id in fixture_ids:
            raise ValueError(f"duplicate fixture_id: {fixture_id}")
        if runtime_path in runtime_paths:
            raise ValueError(
                f"duplicate fixture logical_runtime_path: {runtime_path}"
            )
        fixture_ids.add(fixture_id)
        runtime_paths.add(runtime_path)
        try:
            raw = base64.b64decode(
                fixture["raw_base64"], validate=True
            )
        except (KeyError, binascii.Error, ValueError) as exc:
            raise ValueError(
                f"invalid fixture base64: {fixture_id}"
            ) from exc
        raw_sha256 = sha256_hex_bytes(raw)
        if fixture.get("byte_size") != len(raw):
            raise ValueError(f"fixture byte_size mismatch: {fixture_id}")
        if fixture.get("raw_sha256") != raw_sha256:
            raise ValueError(f"fixture raw_sha256 mismatch: {fixture_id}")
        if fixture.get("content_id") != f"sha256:{raw_sha256}":
            raise ValueError(f"fixture content_id mismatch: {fixture_id}")
        if fixture.get("media_type") == "application/json":
            value = loads_json(raw, source=str(fixture_id))
            if raw != jcs_bytes(value):
                raise ValueError(f"fixture JSON is not JCS: {fixture_id}")
            if fixture.get("jcs_sha256") != sha256_hex(value):
                raise ValueError(
                    f"fixture jcs_sha256 mismatch: {fixture_id}"
                )
        elif fixture.get("jcs_sha256") is not None:
            raise ValueError(
                f"non-JSON fixture has jcs_sha256: {fixture_id}"
            )


def build_property_materialization_bundle(
    envelope: dict[str, Any],
    runner_input: dict[str, Any],
    fixtures: list[dict[str, Any]],
    *,
    schema_dir: str | Path,
    bound_subject_schema_name: str,
) -> dict[str, Any]:
    schema_path = Path(schema_dir).resolve()
    validator = local_schema_bundle(str(schema_path))
    runner_errors = validator.errors(
        runner_input, "evaluation_runner_input.v1.schema.json"
    )
    if runner_errors:
        raise ValueError(f"runner input schema invalid: {runner_errors}")
    subject = runner_input["subject"]
    if subject.get("schema_version") == "UnvalidatedCandidate.v1":
        candidate_errors = validator.errors(
            subject, "unvalidated_candidate.v1.schema.json"
        )
        if candidate_errors:
            raise ValueError(
                f"unvalidated candidate envelope invalid: {candidate_errors}"
            )
        production_errors = validator.errors(
            subject["candidate"], bound_subject_schema_name
        )
        if not production_errors:
            raise ValueError(
                "unvalidated candidate unexpectedly passes production schema"
            )
    else:
        subject_errors = validator.errors(
            subject, bound_subject_schema_name
        )
        if subject_errors:
            raise ValueError(
                f"bound production subject invalid: {subject_errors}"
            )
    _validate_materialized_fixtures(fixtures)
    fixture_refs = runner_input["fixture_refs"]
    fixture_ids = [item["fixture_id"] for item in fixtures]
    if fixture_refs != fixture_ids:
        raise ValueError("runner fixture_refs do not exactly bind fixtures")
    bundle = {
        "schema_version": PROPERTY_BUNDLE_SCHEMA_VERSION,
        "suite_id": envelope["suite_id"],
        "ordinal": envelope["ordinal"],
        "instance_id": envelope["instance_id"],
        "case_id": envelope["case_id"],
        "envelope_sha256": envelope["envelope_sha256"],
        "runner_input": copy.deepcopy(runner_input),
        "sut_materialized_fixtures": copy.deepcopy(fixtures),
        "sut_materialized_fixtures_jcs_sha256": sha256_hex(fixtures),
    }
    bundle = with_self_hash(bundle, "bundle_sha256", prefix=True)
    bundle_errors = validator.errors(
        bundle, "property_materialization_bundle.v1.schema.json"
    )
    if bundle_errors:
        raise ValueError(
            f"property materialization bundle invalid: {bundle_errors}"
        )
    return bundle


def wrap_schema_invalid_candidate(
    candidate: Any,
    *,
    intended_schema_id: str,
    declared_candidate_schema_version: str | None,
    rejection_count: int,
) -> dict[str, Any]:
    if rejection_count < 1:
        raise ValueError("schema-invalid candidate requires a rejection")
    return {
        "schema_version": "UnvalidatedCandidate.v1",
        "intended_schema_id": intended_schema_id,
        "declared_candidate_schema_version": (
            declared_candidate_schema_version
        ),
        "candidate": copy.deepcopy(candidate),
        "candidate_sha256": sha256_hex(candidate),
        "expected_rejection_ids": [
            f"REJECTION-SCHEMA-{index:04d}"
            for index in range(1, rejection_count + 1)
        ],
    }
