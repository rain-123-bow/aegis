from __future__ import annotations

import re


_IDENTIFIER_RE = re.compile(r"^[a-z_][a-z0-9_]*$")


def validate_identifier(value: str) -> str:
    if not _IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"unsafe SQL identifier: {value!r}")
    return value


def build_init_sql(
    *,
    schema: str = "reasoning_ledger",
    embedding_dimensions: int = 1536,
) -> str:
    """Build the version-2 authority schema.

    PostgreSQL rows in the authority layer are append-only. Current state is a
    projection, and vector data is a disposable index bound to an explicit
    embedding profile.
    """

    schema_name = validate_identifier(schema)
    if embedding_dimensions <= 0:
        raise ValueError("embedding_dimensions must be > 0")

    return f"""
CREATE EXTENSION IF NOT EXISTS vector;
CREATE SCHEMA IF NOT EXISTS {schema_name};

CREATE TABLE IF NOT EXISTS {schema_name}.statement (
  project_id text NOT NULL,
  statement_id text NOT NULL,
  created_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (project_id, statement_id)
);

CREATE TABLE IF NOT EXISTS {schema_name}.evidence_descriptor (
  project_id text NOT NULL,
  evidence_id text NOT NULL,
  path text NOT NULL,
  size bigint NOT NULL CHECK (size >= 0),
  sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{{64}}$'),
  source_identity jsonb NOT NULL,
  captured_at timestamptz NOT NULL,
  scope jsonb NOT NULL DEFAULT '{{}}'::jsonb CHECK (
    NOT scope ? 'required_permissions'
    OR jsonb_typeof(scope->'required_permissions') = 'array'
  ),
  content_sha256 text NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{{64}}$'),
  created_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (project_id, evidence_id),
  UNIQUE (project_id, content_sha256)
);

CREATE TABLE IF NOT EXISTS {schema_name}.statement_revision (
  project_id text NOT NULL,
  statement_id text NOT NULL,
  revision integer NOT NULL CHECK (revision >= 1),
  statement_type text NOT NULL CHECK (
    statement_type IN (
      'OBSERVATION', 'FACT', 'CONSTRAINT', 'REQUIREMENT',
      'DECISION', 'RULE', 'HYPOTHESIS', 'CLAIM'
    )
  ),
  content text NOT NULL CHECK (length(content) > 0),
  structured_conditions jsonb NOT NULL DEFAULT '{{}}'::jsonb,
  validity text NOT NULL CHECK (
    validity IN ('ACTIVE', 'STALE', 'INVALID', 'SUPERSEDED')
  ),
  scope jsonb NOT NULL DEFAULT '{{}}'::jsonb CHECK (
    NOT scope ? 'required_permissions'
    OR jsonb_typeof(scope->'required_permissions') = 'array'
  ),
  confidence double precision CHECK (
    confidence IS NULL OR (
      confidence BETWEEN 0 AND 1
      AND confidence <> 'NaN'::double precision
    )
  ),
  content_sha256 text NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{{64}}$'),
  created_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  search_document tsvector GENERATED ALWAYS AS (
    to_tsvector('simple', statement_id || ' ' || content)
  ) STORED,
  PRIMARY KEY (project_id, statement_id, revision),
  UNIQUE (project_id, statement_id, content_sha256),
  FOREIGN KEY (project_id, statement_id)
    REFERENCES {schema_name}.statement(project_id, statement_id)
    ON UPDATE RESTRICT ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS {schema_name}.statement_revision_evidence (
  project_id text NOT NULL,
  statement_id text NOT NULL,
  revision integer NOT NULL,
  evidence_id text NOT NULL,
  ordinal integer NOT NULL CHECK (ordinal >= 0),
  PRIMARY KEY (project_id, statement_id, revision, evidence_id),
  UNIQUE (project_id, statement_id, revision, ordinal),
  FOREIGN KEY (project_id, statement_id, revision)
    REFERENCES {schema_name}.statement_revision(project_id, statement_id, revision)
    ON UPDATE RESTRICT ON DELETE RESTRICT,
  FOREIGN KEY (project_id, evidence_id)
    REFERENCES {schema_name}.evidence_descriptor(project_id, evidence_id)
    ON UPDATE RESTRICT ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS {schema_name}.relation (
  project_id text NOT NULL,
  relation_id text NOT NULL,
  from_statement_id text NOT NULL,
  from_revision integer NOT NULL,
  to_statement_id text NOT NULL,
  to_revision integer NOT NULL,
  relation_type text NOT NULL CHECK (
    relation_type IN (
      'SUPPORTS', 'REFUTES', 'ASSUMES', 'SUPERSEDES',
      'CAUSES', 'ENABLES', 'PREVENTS', 'REQUIRES'
    )
  ),
  applicable_conditions jsonb NOT NULL DEFAULT '{{}}'::jsonb,
  reason text NOT NULL CHECK (length(reason) > 0),
  content_sha256 text NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{{64}}$'),
  created_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (project_id, relation_id),
  UNIQUE (
    project_id, from_statement_id, from_revision,
    to_statement_id, to_revision, relation_type, content_sha256
  ),
  CHECK (
    from_statement_id <> to_statement_id OR from_revision <> to_revision
  ),
  FOREIGN KEY (project_id, from_statement_id, from_revision)
    REFERENCES {schema_name}.statement_revision(project_id, statement_id, revision)
    ON UPDATE RESTRICT ON DELETE RESTRICT,
  FOREIGN KEY (project_id, to_statement_id, to_revision)
    REFERENCES {schema_name}.statement_revision(project_id, statement_id, revision)
    ON UPDATE RESTRICT ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS {schema_name}.relation_evidence (
  project_id text NOT NULL,
  relation_id text NOT NULL,
  evidence_id text NOT NULL,
  ordinal integer NOT NULL CHECK (ordinal >= 0),
  PRIMARY KEY (project_id, relation_id, evidence_id),
  UNIQUE (project_id, relation_id, ordinal),
  FOREIGN KEY (project_id, relation_id)
    REFERENCES {schema_name}.relation(project_id, relation_id)
    ON UPDATE RESTRICT ON DELETE RESTRICT,
  FOREIGN KEY (project_id, evidence_id)
    REFERENCES {schema_name}.evidence_descriptor(project_id, evidence_id)
    ON UPDATE RESTRICT ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS {schema_name}.ledger_event (
  project_id text NOT NULL,
  event_id bigserial NOT NULL,
  aggregate_kind text NOT NULL CHECK (
    aggregate_kind IN ('STATEMENT', 'REVISION', 'RELATION', 'EVIDENCE', 'INDEX', 'PROJECT')
  ),
  aggregate_id text NOT NULL,
  event_type text NOT NULL CHECK (
    event_type IN (
      'STATEMENT_CREATED', 'REVISION_CREATED', 'REVISION_INVALIDATED',
      'REVISION_MARKED_STALE', 'REVISION_REVALIDATED', 'REVISION_SUPERSEDED',
      'RELATION_CREATED', 'EVIDENCE_REGISTERED', 'EMBEDDING_PROFILE_REGISTERED',
      'EMBEDDING_REBUILT'
    )
  ),
  reason text NOT NULL CHECK (length(reason) > 0),
  payload jsonb NOT NULL DEFAULT '{{}}'::jsonb,
  created_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (project_id, event_id)
);

CREATE TABLE IF NOT EXISTS {schema_name}.current_projection (
  project_id text NOT NULL,
  statement_id text NOT NULL,
  revision integer NOT NULL,
  validity text NOT NULL CHECK (
    validity IN ('ACTIVE', 'STALE', 'INVALID', 'SUPERSEDED')
  ),
  projection_event_id bigint NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (project_id, statement_id),
  FOREIGN KEY (project_id, statement_id, revision)
    REFERENCES {schema_name}.statement_revision(project_id, statement_id, revision)
    ON UPDATE RESTRICT ON DELETE RESTRICT,
  FOREIGN KEY (project_id, projection_event_id)
    REFERENCES {schema_name}.ledger_event(project_id, event_id)
    ON UPDATE RESTRICT ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS {schema_name}.embedding_profile (
  project_id text NOT NULL,
  profile_id text NOT NULL,
  provider text NOT NULL,
  model text NOT NULL,
  model_version text NOT NULL,
  dimensions integer NOT NULL CHECK (dimensions > 0),
  normalization text NOT NULL,
  input_template_version text NOT NULL,
  content_sha256 text NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{{64}}$'),
  created_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (project_id, profile_id),
  UNIQUE (project_id, content_sha256)
);

CREATE TABLE IF NOT EXISTS {schema_name}.statement_embedding (
  project_id text NOT NULL,
  statement_id text NOT NULL,
  revision integer NOT NULL,
  profile_id text NOT NULL,
  embedding vector({embedding_dimensions}) NOT NULL,
  embedded_text_sha256 text NOT NULL CHECK (embedded_text_sha256 ~ '^[0-9a-f]{{64}}$'),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (project_id, statement_id, revision, profile_id),
  FOREIGN KEY (project_id, statement_id, revision)
    REFERENCES {schema_name}.statement_revision(project_id, statement_id, revision)
    ON UPDATE RESTRICT ON DELETE RESTRICT,
  FOREIGN KEY (project_id, profile_id)
    REFERENCES {schema_name}.embedding_profile(project_id, profile_id)
    ON UPDATE RESTRICT ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS {schema_name}.schema_metadata (
  key text PRIMARY KEY,
  value jsonb NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE OR REPLACE FUNCTION {schema_name}.reject_authority_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  RAISE EXCEPTION 'reasoning-ledger authority rows are immutable';
END;
$$;

CREATE OR REPLACE FUNCTION {schema_name}.validate_current_projection_event()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
  linked_event {schema_name}.ledger_event%ROWTYPE;
  revision_key text;
  declared_validity text;
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'reasoning-ledger current projections cannot be deleted';
  END IF;
  IF TG_OP = 'UPDATE' AND (
    NEW.project_id <> OLD.project_id
    OR NEW.statement_id <> OLD.statement_id
    OR NEW.projection_event_id <= OLD.projection_event_id
  ) THEN
    RAISE EXCEPTION 'reasoning-ledger projection identity or event order is invalid';
  END IF;
  SELECT * INTO linked_event
  FROM {schema_name}.ledger_event
  WHERE project_id = NEW.project_id
    AND event_id = NEW.projection_event_id;
  IF NOT FOUND OR linked_event.aggregate_kind <> 'REVISION' THEN
    RAISE EXCEPTION 'reasoning-ledger projection has no revision event';
  END IF;
  revision_key := NEW.statement_id || '@' || NEW.revision::text;
  IF linked_event.event_type = 'REVISION_SUPERSEDED' THEN
    IF linked_event.payload->>'superseded_by' <> revision_key THEN
      RAISE EXCEPTION 'reasoning-ledger supersede event targets another revision';
    END IF;
    declared_validity := linked_event.payload->>'new_validity';
  ELSE
    IF linked_event.aggregate_id <> revision_key THEN
      RAISE EXCEPTION 'reasoning-ledger projection event targets another revision';
    END IF;
    declared_validity := linked_event.payload->>'validity';
  END IF;
  IF declared_validity IS NULL OR declared_validity <> NEW.validity THEN
    RAISE EXCEPTION 'reasoning-ledger projection validity differs from its event';
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS statement_immutable ON {schema_name}.statement;
CREATE TRIGGER statement_immutable
BEFORE UPDATE OR DELETE ON {schema_name}.statement
FOR EACH ROW EXECUTE FUNCTION {schema_name}.reject_authority_mutation();

DROP TRIGGER IF EXISTS evidence_descriptor_immutable ON {schema_name}.evidence_descriptor;
CREATE TRIGGER evidence_descriptor_immutable
BEFORE UPDATE OR DELETE ON {schema_name}.evidence_descriptor
FOR EACH ROW EXECUTE FUNCTION {schema_name}.reject_authority_mutation();

DROP TRIGGER IF EXISTS statement_revision_immutable ON {schema_name}.statement_revision;
CREATE TRIGGER statement_revision_immutable
BEFORE UPDATE OR DELETE ON {schema_name}.statement_revision
FOR EACH ROW EXECUTE FUNCTION {schema_name}.reject_authority_mutation();

DROP TRIGGER IF EXISTS statement_revision_evidence_immutable ON {schema_name}.statement_revision_evidence;
CREATE TRIGGER statement_revision_evidence_immutable
BEFORE UPDATE OR DELETE ON {schema_name}.statement_revision_evidence
FOR EACH ROW EXECUTE FUNCTION {schema_name}.reject_authority_mutation();

DROP TRIGGER IF EXISTS relation_immutable ON {schema_name}.relation;
CREATE TRIGGER relation_immutable
BEFORE UPDATE OR DELETE ON {schema_name}.relation
FOR EACH ROW EXECUTE FUNCTION {schema_name}.reject_authority_mutation();

DROP TRIGGER IF EXISTS relation_evidence_immutable ON {schema_name}.relation_evidence;
CREATE TRIGGER relation_evidence_immutable
BEFORE UPDATE OR DELETE ON {schema_name}.relation_evidence
FOR EACH ROW EXECUTE FUNCTION {schema_name}.reject_authority_mutation();

DROP TRIGGER IF EXISTS ledger_event_immutable ON {schema_name}.ledger_event;
CREATE TRIGGER ledger_event_immutable
BEFORE UPDATE OR DELETE ON {schema_name}.ledger_event
FOR EACH ROW EXECUTE FUNCTION {schema_name}.reject_authority_mutation();

DROP TRIGGER IF EXISTS embedding_profile_immutable ON {schema_name}.embedding_profile;
CREATE TRIGGER embedding_profile_immutable
BEFORE UPDATE OR DELETE ON {schema_name}.embedding_profile
FOR EACH ROW EXECUTE FUNCTION {schema_name}.reject_authority_mutation();

DROP TRIGGER IF EXISTS current_projection_event_bound ON {schema_name}.current_projection;
CREATE TRIGGER current_projection_event_bound
BEFORE INSERT OR UPDATE OR DELETE ON {schema_name}.current_projection
FOR EACH ROW EXECUTE FUNCTION {schema_name}.validate_current_projection_event();

INSERT INTO {schema_name}.schema_metadata(key, value)
VALUES (
  'schema_version',
  jsonb_build_object(
    'name', 'reasoning_ledger',
    'version', 2,
    'embedding_dimensions', {embedding_dimensions},
    'authority_model', 'immutable_revision_event_projection'
  )
)
ON CONFLICT (key)
DO UPDATE SET value = EXCLUDED.value, updated_at = now();

CREATE INDEX IF NOT EXISTS statement_revision_project_type_idx
ON {schema_name}.statement_revision(project_id, statement_type, created_at DESC);

CREATE INDEX IF NOT EXISTS statement_revision_scope_gin_idx
ON {schema_name}.statement_revision USING gin(scope);

CREATE INDEX IF NOT EXISTS statement_revision_search_gin_idx
ON {schema_name}.statement_revision USING gin(search_document);

CREATE INDEX IF NOT EXISTS relation_from_idx
ON {schema_name}.relation(project_id, from_statement_id, from_revision, relation_type);

CREATE INDEX IF NOT EXISTS relation_to_idx
ON {schema_name}.relation(project_id, to_statement_id, to_revision, relation_type);

CREATE INDEX IF NOT EXISTS ledger_event_aggregate_idx
ON {schema_name}.ledger_event(project_id, aggregate_kind, aggregate_id, event_id);

CREATE INDEX IF NOT EXISTS current_projection_validity_idx
ON {schema_name}.current_projection(project_id, validity, statement_id);
""".strip()
