from __future__ import annotations

import re


_IDENTIFIER_RE = re.compile(r"^[a-z_][a-z0-9_]*$")


def validate_identifier(value: str) -> str:
    if not _IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"unsafe SQL identifier: {value!r}")
    return value


def build_init_sql(*, schema: str = "reasoning_ledger", embedding_dimensions: int = 1536) -> str:
    schema_name = validate_identifier(schema)
    if embedding_dimensions <= 0:
        raise ValueError("embedding_dimensions must be > 0")

    return f"""
CREATE EXTENSION IF NOT EXISTS vector;
CREATE SCHEMA IF NOT EXISTS {schema_name};

CREATE TABLE IF NOT EXISTS {schema_name}.reasoning_item (
  project_id text NOT NULL,
  id text NOT NULL,
  type text NOT NULL CHECK (type IN ('input', 'fact', 'rule', 'claim')),
  status text NOT NULL CHECK (status IN ('active', 'stale', 'invalid', 'superseded')),
  scope jsonb NOT NULL DEFAULT '{{}}'::jsonb,
  content text NOT NULL,
  artifact_path text,
  source text,
  evidence_path text,
  confidence double precision CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),
  level integer NOT NULL DEFAULT 0 CHECK (level >= 0),
  version integer NOT NULL DEFAULT 1 CHECK (version >= 1),
  embedding vector({embedding_dimensions}),
  metadata jsonb NOT NULL DEFAULT '{{}}'::jsonb,
  created_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (project_id, id)
);

CREATE TABLE IF NOT EXISTS {schema_name}.reasoning_edge (
  project_id text NOT NULL,
  id bigserial NOT NULL,
  from_id text NOT NULL,
  to_id text NOT NULL,
  relation text NOT NULL CHECK (relation IN ('supports', 'refutes', 'assumes', 'supersedes')),
  status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive')),
  reason text NOT NULL,
  confidence double precision CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),
  metadata jsonb NOT NULL DEFAULT '{{}}'::jsonb,
  created_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (project_id, id),
  CHECK (from_id <> to_id),
  FOREIGN KEY (project_id, from_id)
    REFERENCES {schema_name}.reasoning_item(project_id, id)
    ON UPDATE CASCADE ON DELETE RESTRICT,
  FOREIGN KEY (project_id, to_id)
    REFERENCES {schema_name}.reasoning_item(project_id, id)
    ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS {schema_name}.reasoning_event (
  project_id text NOT NULL,
  id bigserial NOT NULL,
  target_kind text NOT NULL CHECK (target_kind IN ('item', 'edge', 'index', 'project')),
  target_id text NOT NULL,
  event_type text NOT NULL CHECK (
    event_type IN (
      'created',
      'linked',
      'invalidated',
      'marked_stale',
      'revalidated',
      'superseded',
      'index_rebuilt'
    )
  ),
  reason text NOT NULL,
  payload jsonb NOT NULL DEFAULT '{{}}'::jsonb,
  created_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (project_id, id)
);

CREATE TABLE IF NOT EXISTS {schema_name}.schema_metadata (
  key text PRIMARY KEY,
  value jsonb NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE OR REPLACE FUNCTION {schema_name}.set_reasoning_item_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS reasoning_item_updated_at
ON {schema_name}.reasoning_item;

CREATE TRIGGER reasoning_item_updated_at
BEFORE UPDATE ON {schema_name}.reasoning_item
FOR EACH ROW
EXECUTE FUNCTION {schema_name}.set_reasoning_item_updated_at();

INSERT INTO {schema_name}.schema_metadata(key, value)
VALUES (
  'schema_version',
  jsonb_build_object(
    'name', 'reasoning_ledger',
    'version', 1,
    'embedding_dimensions', {embedding_dimensions}
  )
)
ON CONFLICT (key)
DO UPDATE SET value = EXCLUDED.value, updated_at = now();

CREATE INDEX IF NOT EXISTS reasoning_item_project_status_idx
ON {schema_name}.reasoning_item(project_id, status);

CREATE INDEX IF NOT EXISTS reasoning_item_project_type_idx
ON {schema_name}.reasoning_item(project_id, type);

CREATE INDEX IF NOT EXISTS reasoning_item_scope_gin_idx
ON {schema_name}.reasoning_item
USING gin(scope);

CREATE INDEX IF NOT EXISTS reasoning_edge_from_idx
ON {schema_name}.reasoning_edge(project_id, from_id)
WHERE status = 'active';

CREATE INDEX IF NOT EXISTS reasoning_edge_to_idx
ON {schema_name}.reasoning_edge(project_id, to_id)
WHERE status = 'active';

CREATE INDEX IF NOT EXISTS reasoning_event_target_idx
ON {schema_name}.reasoning_event(project_id, target_kind, target_id);

CREATE INDEX IF NOT EXISTS reasoning_item_embedding_hnsw_idx
ON {schema_name}.reasoning_item
USING hnsw (embedding vector_cosine_ops)
WHERE embedding IS NOT NULL;
""".strip()
