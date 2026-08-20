from __future__ import annotations

from pathlib import Path
from typing import Any

from .closure_materialization_data import (
    MATERIALIZER_ID,
    build_closure_materialization,
)
from .materialization import (
    BLOCKER_RECORD_SCHEMA_ID,
    build_property_materialization_bundle,
    validate_property_envelope,
)


def materialize_closure_bundle(
    envelope: dict[str, Any],
    *,
    suite: dict[str, Any],
    schema_dir: str | Path,
) -> dict[str, Any]:
    """Build the runner channel without reading an oracle result."""

    validate_property_envelope(envelope, suite, schema_dir=schema_dir)
    runner_input, fixtures = build_closure_materialization(
        envelope, suite=suite, schema_dir=schema_dir
    )
    return build_property_materialization_bundle(
        envelope,
        runner_input,
        fixtures,
        schema_dir=schema_dir,
        bound_subject_schema_name=Path(BLOCKER_RECORD_SCHEMA_ID).name,
    )


__all__ = ["MATERIALIZER_ID", "materialize_closure_bundle"]
