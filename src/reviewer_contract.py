from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any


MASTER_REVIEWER = "MASTER_REVIEWER"
TEST_PLAN_REVIEWER = "TEST_PLAN_REVIEWER"
TEST_RESULT_REVIEWER = "TEST_RESULT_REVIEWER"
FINAL_REVIEWER = "FINAL_REVIEWER"

REVIEWER_ROLES = frozenset(
    {
        MASTER_REVIEWER,
        TEST_PLAN_REVIEWER,
        TEST_RESULT_REVIEWER,
        FINAL_REVIEWER,
    }
)
REVIEW_CONCLUSIONS = frozenset({"PASS", "FAIL", "UNDETERMINED"})

_ENGINEERING_CATEGORIES = frozenset(
    {
        "REQUIREMENT_DEFECT",
        "IMPLEMENTATION_PLAN_DEFECT",
        "REQUIRED_INPUT_MISSING",
        "EVIDENCE_MISSING",
        "LOGIC_GAP",
    }
)
ROLE_FINDING_CATEGORIES = {
    MASTER_REVIEWER: _ENGINEERING_CATEGORIES,
    TEST_PLAN_REVIEWER: _ENGINEERING_CATEGORIES | {"TEST_PLAN_DEFECT"},
    TEST_RESULT_REVIEWER: _ENGINEERING_CATEGORIES
    | {
        "TEST_PLAN_DEFECT",
        "EXECUTION_INCOMPLETE",
    },
    FINAL_REVIEWER: _ENGINEERING_CATEGORIES
    | {
        "TEST_PLAN_DEFECT",
        "EXECUTION_INCOMPLETE",
        "CODE_DEFECT",
        "TEST_REPORT_DEFECT",
        "REASONING_DEFECT",
        "GOVERNANCE_DEFECT",
    },
}

_OUTPUT_FIELDS = frozenset(
    {
        "artifact_path",
        "reasoning_ledger_context_pack",
        "review_conclusion",
        "finding_categories",
        "findings",
        "review_output_artifacts",
    }
)
_FINDING_FIELDS = frozenset(
    {"finding_id", "category", "summary", "reasoning", "evidence_ids"}
)
_ARTIFACT_FIELDS = frozenset({"artifact_id", "path", "size", "sha256"})
_ARTIFACT_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_FORBIDDEN_WORKFLOW_SEMANTICS_PATTERN = re.compile(
    r"\b(?:"
    r"RETURN_TO_[A-Z0-9_]+|"
    r"ROUTE_TO|NEXT_(?:NODE|ROLE)|TARGET_(?:NODE|ROLE)|"
    r"MASTER_PROCESSING|TEST_PLAN_AUTHORING|TEST_EXECUTION|TEST_REPORTING|"
    r"REVIEW_BLOCKED|TEST_PLAN_AUTHOR|TEST_EXECUTOR|TEST_REPORT_WRITER"
    r")\b",
    re.IGNORECASE,
)


class ReviewContractError(ValueError):
    pass


def complete_reviewer_model_output(
    payload: Mapping[str, object],
) -> dict[str, object]:
    completed = dict(payload)
    if "finding_categories" in completed:
        return completed
    findings = completed.get("findings")
    if not isinstance(findings, list):
        raise ReviewContractError("reviewer model output findings must be an array")
    categories: set[str] = set()
    for finding in findings:
        if not isinstance(finding, Mapping) or not isinstance(
            finding.get("category"), str
        ):
            raise ReviewContractError(
                "reviewer model output finding category is invalid"
            )
        categories.add(str(finding["category"]))
    completed["finding_categories"] = sorted(categories)
    return completed


def reviewer_output_schema(role: str) -> dict[str, Any]:
    categories = sorted(_categories_for_role(role))
    artifact_descriptor = {
        "type": "object",
        "additionalProperties": False,
        "required": ["artifact_id", "path", "size", "sha256"],
        "properties": {
            "artifact_id": {
                "type": "string",
                "pattern": _ARTIFACT_ID_PATTERN.pattern,
            },
            "path": {"type": "string", "minLength": 1},
            "size": {"type": "integer", "minimum": 1},
            "sha256": {"type": "string", "pattern": _SHA256_PATTERN.pattern},
        },
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"aegis.reviewer_output.{role.lower()}.v1",
        "type": "object",
        "additionalProperties": False,
        "required": sorted(_OUTPUT_FIELDS),
        "properties": {
            "artifact_path": {"type": "string", "minLength": 1},
            "reasoning_ledger_context_pack": {
                "type": "string",
                "minLength": 1,
            },
            "review_conclusion": {
                "type": "string",
                "enum": sorted(REVIEW_CONCLUSIONS),
            },
            "finding_categories": {
                "type": "array",
                "uniqueItems": True,
                "items": {"type": "string", "enum": categories},
            },
            "findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": sorted(_FINDING_FIELDS),
                    "properties": {
                        "finding_id": {"type": "string", "minLength": 1},
                        "category": {"type": "string", "enum": categories},
                        "summary": {"type": "string", "minLength": 1},
                        "reasoning": {"type": "string", "minLength": 1},
                        "evidence_ids": {
                            "type": "array",
                            "minItems": 1,
                            "uniqueItems": True,
                            "items": {"type": "string", "minLength": 1},
                        },
                    },
                },
            },
            "review_output_artifacts": {
                "type": "array",
                "minItems": 1,
                "items": artifact_descriptor,
            },
        },
    }


def validate_reviewer_output(
    role: str,
    payload: Mapping[str, object],
) -> dict[str, object]:
    categories_allowed = _categories_for_role(role)
    if not isinstance(payload, Mapping):
        raise ReviewContractError("review output must be an object")
    fields = set(payload)
    unsupported = sorted(fields - _OUTPUT_FIELDS)
    if unsupported:
        raise ReviewContractError(
            "review output contains unsupported fields: " + ", ".join(unsupported)
        )
    missing = sorted(_OUTPUT_FIELDS - fields)
    if missing:
        raise ReviewContractError(
            "review output is missing required fields: " + ", ".join(missing)
        )

    artifact_path = _nonempty_string(payload.get("artifact_path"), "artifact_path")
    context_path = _nonempty_string(
        payload.get("reasoning_ledger_context_pack"),
        "reasoning_ledger_context_pack",
    )
    conclusion = payload.get("review_conclusion")
    if conclusion not in REVIEW_CONCLUSIONS:
        raise ReviewContractError("review_conclusion is invalid")

    raw_categories = payload.get("finding_categories")
    if not isinstance(raw_categories, list) or not all(
        isinstance(category, str) for category in raw_categories
    ):
        raise ReviewContractError("finding_categories must be a string array")
    if len(raw_categories) != len(set(raw_categories)):
        raise ReviewContractError("finding_categories contains duplicates")
    unknown_categories = sorted(set(raw_categories) - categories_allowed)
    if unknown_categories:
        raise ReviewContractError(
            f"{role} returned unsupported finding categories: "
            + ", ".join(unknown_categories)
        )

    raw_findings = payload.get("findings")
    if not isinstance(raw_findings, list):
        raise ReviewContractError("findings must be an array")
    findings: list[dict[str, object]] = []
    finding_ids: set[str] = set()
    finding_categories: set[str] = set()
    for raw_finding in raw_findings:
        finding = _validate_finding(raw_finding, categories_allowed)
        finding_id = str(finding["finding_id"])
        if finding_id in finding_ids:
            raise ReviewContractError("findings contain duplicate finding IDs")
        finding_ids.add(finding_id)
        finding_categories.add(str(finding["category"]))
        findings.append(finding)

    declared_categories = set(raw_categories)
    if conclusion == "PASS":
        if declared_categories or findings:
            raise ReviewContractError("PASS review cannot contain findings")
    else:
        if not declared_categories or not findings:
            raise ReviewContractError(
                f"{conclusion} review must contain categorized findings"
            )
        if declared_categories != finding_categories:
            raise ReviewContractError(
                "declared finding categories do not match finding categories"
            )

    artifacts = _validate_artifacts(payload.get("review_output_artifacts"))
    findings.sort(key=lambda item: str(item["finding_id"]))
    return {
        "artifact_path": artifact_path,
        "reasoning_ledger_context_pack": context_path,
        "review_conclusion": conclusion,
        "finding_categories": sorted(declared_categories),
        "findings": findings,
        "review_output_artifacts": artifacts,
    }


def coordinator_review_stage(
    role: str,
    payload: Mapping[str, object],
) -> str:
    validated = validate_reviewer_output(role, payload)
    conclusion = validated["review_conclusion"]
    categories = set(validated["finding_categories"])
    if role in {MASTER_REVIEWER, FINAL_REVIEWER}:
        return "END"
    if conclusion == "UNDETERMINED":
        return "REVIEW_BLOCKED"
    if conclusion == "PASS":
        return (
            "TEST_EXECUTION"
            if role == TEST_PLAN_REVIEWER
            else "TEST_REPORTING"
        )
    if categories & {"REQUIREMENT_DEFECT", "IMPLEMENTATION_PLAN_DEFECT"}:
        return "MASTER_PROCESSING"
    if role == TEST_PLAN_REVIEWER or "TEST_PLAN_DEFECT" in categories:
        return "TEST_PLAN_AUTHORING"
    if role == TEST_RESULT_REVIEWER and categories & {
        "EXECUTION_INCOMPLETE",
        "EVIDENCE_MISSING",
    }:
        return "TEST_EXECUTION"
    return "REVIEW_BLOCKED"


def _categories_for_role(role: str) -> frozenset[str]:
    categories = ROLE_FINDING_CATEGORIES.get(role)
    if categories is None:
        raise ReviewContractError(f"unsupported reviewer role: {role}")
    return categories


def _nonempty_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReviewContractError(f"{field} must be a non-empty string")
    return value


def _validate_finding(
    raw: object,
    categories_allowed: frozenset[str],
) -> dict[str, object]:
    if not isinstance(raw, Mapping):
        raise ReviewContractError("each finding must be an object")
    fields = set(raw)
    if fields != _FINDING_FIELDS:
        raise ReviewContractError("finding fields do not match the contract")
    category = raw.get("category")
    if category not in categories_allowed:
        raise ReviewContractError("finding category is invalid for this reviewer")
    evidence_ids = raw.get("evidence_ids")
    if (
        not isinstance(evidence_ids, list)
        or not evidence_ids
        or not all(isinstance(item, str) and item.strip() for item in evidence_ids)
        or len(evidence_ids) != len(set(evidence_ids))
    ):
        raise ReviewContractError(
            "finding evidence_ids must be a unique non-empty string array"
        )
    textual_values = [
        raw.get("finding_id"),
        raw.get("summary"),
        raw.get("reasoning"),
        *evidence_ids,
    ]
    if any(
        isinstance(value, str)
        and _FORBIDDEN_WORKFLOW_SEMANTICS_PATTERN.search(value) is not None
        for value in textual_values
    ):
        raise ReviewContractError("review finding contains workflow semantics")
    return {
        "finding_id": _nonempty_string(raw.get("finding_id"), "finding_id"),
        "category": str(category),
        "summary": _nonempty_string(raw.get("summary"), "summary"),
        "reasoning": _nonempty_string(raw.get("reasoning"), "reasoning"),
        "evidence_ids": list(evidence_ids),
    }


def _validate_artifacts(raw: object) -> list[dict[str, object]]:
    if not isinstance(raw, list) or not raw:
        raise ReviewContractError("review_output_artifacts must be non-empty")
    artifacts: list[dict[str, object]] = []
    artifact_ids: set[str] = set()
    paths: set[str] = set()
    for value in raw:
        if not isinstance(value, Mapping) or set(value) != _ARTIFACT_FIELDS:
            raise ReviewContractError("review output artifact fields are invalid")
        artifact_id = value.get("artifact_id")
        path = value.get("path")
        size = value.get("size")
        sha256 = value.get("sha256")
        if (
            not isinstance(artifact_id, str)
            or _ARTIFACT_ID_PATTERN.fullmatch(artifact_id) is None
        ):
            raise ReviewContractError("review output artifact ID is invalid")
        if artifact_id in artifact_ids:
            raise ReviewContractError("review output artifact IDs are not unique")
        if not isinstance(path, str) or not path.strip() or path in paths:
            raise ReviewContractError("review output artifact paths are invalid")
        if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
            raise ReviewContractError("review output artifact size is invalid")
        if not isinstance(sha256, str) or _SHA256_PATTERN.fullmatch(sha256) is None:
            raise ReviewContractError("review output artifact SHA-256 is invalid")
        artifact_ids.add(artifact_id)
        paths.add(path)
        artifacts.append(
            {
                "artifact_id": artifact_id,
                "path": path,
                "size": size,
                "sha256": sha256,
            }
        )
    artifacts.sort(key=lambda item: str(item["artifact_id"]))
    return artifacts
