CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;
CREATE SCHEMA IF NOT EXISTS reasoning_ledger;

CREATE OR REPLACE FUNCTION reasoning_ledger.contains_forbidden_authority_key(value jsonb)
RETURNS boolean
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
AS $$
  SELECT pg_catalog.jsonb_path_exists(
    value,
    '$.** ? (@.type() == "object").keyvalue() ? (@.key == "required_permissions")'
  )
$$;

CREATE TABLE IF NOT EXISTS reasoning_ledger.project_anchor (
  project_id text NOT NULL,
  cluster_system_identifier text NOT NULL CHECK (
    cluster_system_identifier ~ '^[0-9]+$'
  ),
  database_oid bigint NOT NULL CHECK (database_oid > 0),
  database_name text NOT NULL CHECK (length(database_name) > 0),
  schema_name text NOT NULL CHECK (length(schema_name) > 0),
  anchor_sha256 text NOT NULL CHECK (anchor_sha256 ~ '^[0-9a-f]{64}$'),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (project_id)
);

CREATE TABLE IF NOT EXISTS reasoning_ledger.statement (
  project_id text NOT NULL,
  statement_id text NOT NULL,
  created_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (project_id, statement_id)
);

CREATE TABLE IF NOT EXISTS reasoning_ledger.evidence_descriptor (
  project_id text NOT NULL,
  evidence_id text NOT NULL,
  path text NOT NULL,
  size bigint NOT NULL CHECK (size >= 0),
  sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  source_identity jsonb NOT NULL,
  captured_at timestamptz NOT NULL,
  scope jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (
    NOT reasoning_ledger.contains_forbidden_authority_key(scope)
  ),
  content_sha256 text NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
  created_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (project_id, evidence_id),
  UNIQUE (project_id, content_sha256)
);

CREATE TABLE IF NOT EXISTS reasoning_ledger.statement_revision (
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
  structured_conditions jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (
    NOT reasoning_ledger.contains_forbidden_authority_key(structured_conditions)
  ),
  validity text NOT NULL CHECK (
    validity IN ('ACTIVE', 'STALE', 'INVALID', 'SUPERSEDED')
  ),
  scope jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (
    NOT reasoning_ledger.contains_forbidden_authority_key(scope)
  ),
  confidence double precision CHECK (
    confidence IS NULL OR (
      confidence BETWEEN 0 AND 1
      AND confidence <> 'NaN'::double precision
    )
  ),
  content_sha256 text NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
  created_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  search_document tsvector GENERATED ALWAYS AS (
    to_tsvector('simple', statement_id || ' ' || content)
  ) STORED,
  PRIMARY KEY (project_id, statement_id, revision),
  UNIQUE (project_id, statement_id, content_sha256),
  FOREIGN KEY (project_id, statement_id)
    REFERENCES reasoning_ledger.statement(project_id, statement_id)
    ON UPDATE RESTRICT ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS reasoning_ledger.statement_revision_evidence (
  project_id text NOT NULL,
  statement_id text NOT NULL,
  revision integer NOT NULL,
  evidence_id text NOT NULL,
  ordinal integer NOT NULL CHECK (ordinal >= 0),
  PRIMARY KEY (project_id, statement_id, revision, evidence_id),
  UNIQUE (project_id, statement_id, revision, ordinal),
  FOREIGN KEY (project_id, statement_id, revision)
    REFERENCES reasoning_ledger.statement_revision(project_id, statement_id, revision)
    ON UPDATE RESTRICT ON DELETE RESTRICT,
  FOREIGN KEY (project_id, evidence_id)
    REFERENCES reasoning_ledger.evidence_descriptor(project_id, evidence_id)
    ON UPDATE RESTRICT ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS reasoning_ledger.relation (
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
  applicable_conditions jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (
    NOT reasoning_ledger.contains_forbidden_authority_key(applicable_conditions)
  ),
  reason text NOT NULL CHECK (length(reason) > 0),
  content_sha256 text NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
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
    REFERENCES reasoning_ledger.statement_revision(project_id, statement_id, revision)
    ON UPDATE RESTRICT ON DELETE RESTRICT,
  FOREIGN KEY (project_id, to_statement_id, to_revision)
    REFERENCES reasoning_ledger.statement_revision(project_id, statement_id, revision)
    ON UPDATE RESTRICT ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS reasoning_ledger.relation_evidence (
  project_id text NOT NULL,
  relation_id text NOT NULL,
  evidence_id text NOT NULL,
  ordinal integer NOT NULL CHECK (ordinal >= 0),
  PRIMARY KEY (project_id, relation_id, evidence_id),
  UNIQUE (project_id, relation_id, ordinal),
  FOREIGN KEY (project_id, relation_id)
    REFERENCES reasoning_ledger.relation(project_id, relation_id)
    ON UPDATE RESTRICT ON DELETE RESTRICT,
  FOREIGN KEY (project_id, evidence_id)
    REFERENCES reasoning_ledger.evidence_descriptor(project_id, evidence_id)
    ON UPDATE RESTRICT ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS reasoning_ledger.ledger_event (
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
      'EMBEDDING_REBUILT', 'INDEX_STORAGE_REINDEXED'
    )
  ),
  reason text NOT NULL CHECK (length(reason) > 0),
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (project_id, event_id)
);

CREATE TABLE IF NOT EXISTS reasoning_ledger.current_projection (
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
    REFERENCES reasoning_ledger.statement_revision(project_id, statement_id, revision)
    ON UPDATE RESTRICT ON DELETE RESTRICT,
  FOREIGN KEY (project_id, projection_event_id)
    REFERENCES reasoning_ledger.ledger_event(project_id, event_id)
    ON UPDATE RESTRICT ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS reasoning_ledger.embedding_profile (
  project_id text NOT NULL,
  profile_id text NOT NULL,
  provider text NOT NULL,
  model text NOT NULL,
  model_version text NOT NULL,
  dimensions integer NOT NULL CHECK (dimensions > 0),
  normalization text NOT NULL,
  input_template_version text NOT NULL,
  content_sha256 text NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
  created_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (project_id, profile_id),
  UNIQUE (project_id, content_sha256)
);

CREATE TABLE IF NOT EXISTS reasoning_ledger.statement_embedding (
  project_id text NOT NULL,
  statement_id text NOT NULL,
  revision integer NOT NULL,
  profile_id text NOT NULL,
  embedding public.vector(1536) NOT NULL,
  embedded_text_sha256 text NOT NULL CHECK (embedded_text_sha256 ~ '^[0-9a-f]{64}$'),
  created_at timestamptz NOT NULL DEFAULT now(),
  embedding_sha256 text NOT NULL CHECK (embedding_sha256 ~ '^[0-9a-f]{64}$'),
  generator_identity jsonb NOT NULL,
  generation_receipt jsonb NOT NULL,
  generation_receipt_sha256 text NOT NULL CHECK (
    generation_receipt_sha256 ~ '^[0-9a-f]{64}$'
  ),
  PRIMARY KEY (project_id, statement_id, revision, profile_id),
  FOREIGN KEY (project_id, statement_id, revision)
    REFERENCES reasoning_ledger.statement_revision(project_id, statement_id, revision)
    ON UPDATE RESTRICT ON DELETE RESTRICT,
  FOREIGN KEY (project_id, profile_id)
    REFERENCES reasoning_ledger.embedding_profile(project_id, profile_id)
    ON UPDATE RESTRICT ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS reasoning_ledger.schema_metadata (
  key text PRIMARY KEY,
  value jsonb NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE OR REPLACE FUNCTION reasoning_ledger.reject_authority_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  RAISE EXCEPTION 'reasoning-ledger authority rows are immutable';
END;
$$;

CREATE OR REPLACE FUNCTION reasoning_ledger.validate_current_projection_event()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
  linked_event reasoning_ledger.ledger_event%ROWTYPE;
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
  FROM reasoning_ledger.ledger_event
  WHERE project_id = NEW.project_id
    AND event_id = NEW.projection_event_id;
  IF NOT FOUND OR linked_event.aggregate_kind <> 'REVISION' THEN
    RAISE EXCEPTION 'reasoning-ledger projection has no revision event';
  END IF;
  IF TG_OP = 'INSERT' AND linked_event.event_type <> 'REVISION_CREATED' THEN
    RAISE EXCEPTION 'reasoning-ledger initial projection event type is invalid';
  ELSIF TG_OP = 'UPDATE' AND NEW.revision <> OLD.revision
        AND linked_event.event_type <> 'REVISION_SUPERSEDED' THEN
    RAISE EXCEPTION 'reasoning-ledger revision transition event type is invalid';
  ELSIF TG_OP = 'UPDATE' AND NEW.revision = OLD.revision
        AND linked_event.event_type <> (CASE NEW.validity
          WHEN 'ACTIVE' THEN 'REVISION_REVALIDATED'
          WHEN 'STALE' THEN 'REVISION_MARKED_STALE'
          WHEN 'INVALID' THEN 'REVISION_INVALIDATED'
          ELSE ''
        END) THEN
    RAISE EXCEPTION 'reasoning-ledger validity projection event type is invalid';
  END IF;
  revision_key := NEW.statement_id || '@' || NEW.revision::text;
  IF linked_event.event_type = 'REVISION_SUPERSEDED' THEN
    IF TG_OP <> 'UPDATE'
       OR NEW.revision <> OLD.revision + 1
       OR linked_event.aggregate_id <> OLD.statement_id || '@' || OLD.revision::text
       OR linked_event.payload->>'superseded_by' <> revision_key THEN
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

CREATE OR REPLACE FUNCTION reasoning_ledger.validate_supersedes_event_transaction()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF NEW.event_type <> 'REVISION_SUPERSEDED' THEN
    RETURN NEW;
  END IF;
  IF NOT EXISTS (
    SELECT 1
    FROM reasoning_ledger.relation relation
    JOIN reasoning_ledger.statement_revision revision
      ON revision.project_id = relation.project_id
     AND revision.statement_id = relation.to_statement_id
     AND revision.revision = relation.to_revision
    JOIN reasoning_ledger.current_projection projection
      ON projection.project_id = relation.project_id
     AND projection.statement_id = relation.to_statement_id
     AND projection.revision = relation.to_revision
     AND projection.projection_event_id = NEW.event_id
    WHERE relation.project_id = NEW.project_id
      AND relation.relation_id = NEW.payload->>'relation_id'
      AND relation.relation_type = 'SUPERSEDES'
      AND relation.from_statement_id || '@' || relation.from_revision::text = NEW.aggregate_id
      AND relation.to_statement_id || '@' || relation.to_revision::text = NEW.payload->>'superseded_by'
      AND revision.validity = 'ACTIVE'
      AND NEW.payload->>'new_validity' = revision.validity
      AND relation.xmin = pg_catalog.pg_current_xact_id()::xid
      AND revision.xmin = pg_catalog.pg_current_xact_id()::xid
      AND projection.xmin = pg_catalog.pg_current_xact_id()::xid
  ) THEN
    RAISE EXCEPTION 'reasoning-ledger supersede event is not bound to one atomic revision/relation/projection transaction';
  END IF;
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION reasoning_ledger.validate_revision_transaction()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF NEW.revision = 1 THEN
    IF NEW.validity = 'SUPERSEDED' OR NOT EXISTS (
      SELECT 1
      FROM reasoning_ledger.current_projection projection
      JOIN reasoning_ledger.ledger_event event
        ON event.project_id = projection.project_id
       AND event.event_id = projection.projection_event_id
      WHERE projection.project_id = NEW.project_id
        AND projection.statement_id = NEW.statement_id
        AND projection.revision = NEW.revision
        AND projection.validity = NEW.validity
        AND projection.xmin = pg_catalog.pg_current_xact_id()::xid
        AND event.event_type = 'REVISION_CREATED'
        AND event.aggregate_id = NEW.statement_id || '@1'
        AND event.xmin = pg_catalog.pg_current_xact_id()::xid
    ) THEN
      RAISE EXCEPTION 'reasoning-ledger initial revision is not bound to one atomic event/projection transaction';
    END IF;
    RETURN NEW;
  END IF;
  IF NEW.validity <> 'ACTIVE' OR NOT EXISTS (
    SELECT 1
    FROM reasoning_ledger.relation relation
    JOIN reasoning_ledger.ledger_event event
      ON event.project_id = relation.project_id
     AND event.event_type = 'REVISION_SUPERSEDED'
     AND event.aggregate_id = relation.from_statement_id || '@' || relation.from_revision::text
     AND event.payload->>'relation_id' = relation.relation_id
     AND event.payload->>'superseded_by' = NEW.statement_id || '@' || NEW.revision::text
    JOIN reasoning_ledger.current_projection projection
      ON projection.project_id = relation.project_id
     AND projection.statement_id = NEW.statement_id
     AND projection.revision = NEW.revision
     AND projection.projection_event_id = event.event_id
    WHERE relation.project_id = NEW.project_id
      AND relation.relation_type = 'SUPERSEDES'
      AND relation.from_statement_id = NEW.statement_id
      AND relation.from_revision = NEW.revision - 1
      AND relation.to_statement_id = NEW.statement_id
      AND relation.to_revision = NEW.revision
      AND relation.xmin = pg_catalog.pg_current_xact_id()::xid
      AND event.xmin = pg_catalog.pg_current_xact_id()::xid
      AND projection.xmin = pg_catalog.pg_current_xact_id()::xid
  ) THEN
    RAISE EXCEPTION 'reasoning-ledger successor revision is not bound to one atomic supersede transaction';
  END IF;
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION reasoning_ledger.validate_supersedes_transaction()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
  projected_revision integer;
BEGIN
  IF NEW.relation_type <> 'SUPERSEDES' THEN
    RETURN NEW;
  END IF;
  IF NEW.from_statement_id <> NEW.to_statement_id
     OR NEW.to_revision <> NEW.from_revision + 1 THEN
    RAISE EXCEPTION 'reasoning-ledger supersedes relation is not a consecutive version transition';
  END IF;
  SELECT revision INTO projected_revision
  FROM reasoning_ledger.current_projection
  WHERE project_id = NEW.project_id
    AND statement_id = NEW.to_statement_id;
  IF projected_revision IS DISTINCT FROM NEW.to_revision THEN
    RAISE EXCEPTION 'reasoning-ledger supersedes relation is not bound to the current projection';
  END IF;
  IF NOT EXISTS (
    SELECT 1
    FROM reasoning_ledger.ledger_event event
    WHERE event.project_id = NEW.project_id
      AND event.event_type = 'REVISION_SUPERSEDED'
      AND event.aggregate_id = NEW.from_statement_id || '@' || NEW.from_revision::text
      AND event.payload->>'superseded_by' = NEW.to_statement_id || '@' || NEW.to_revision::text
      AND event.payload->>'relation_id' = NEW.relation_id
      AND event.xmin = pg_catalog.pg_current_xact_id()::xid
  ) THEN
    RAISE EXCEPTION 'reasoning-ledger supersedes relation has no atomic authority event';
  END IF;
  IF NOT EXISTS (
    SELECT 1
    FROM reasoning_ledger.statement_revision revision
    WHERE revision.project_id = NEW.project_id
      AND revision.statement_id = NEW.to_statement_id
      AND revision.revision = NEW.to_revision
      AND revision.xmin = pg_catalog.pg_current_xact_id()::xid
  ) THEN
    RAISE EXCEPTION 'reasoning-ledger superseding revision was not created in the same transaction';
  END IF;
  IF NOT EXISTS (
    SELECT 1
    FROM reasoning_ledger.current_projection projection
    WHERE projection.project_id = NEW.project_id
      AND projection.statement_id = NEW.to_statement_id
      AND projection.revision = NEW.to_revision
      AND projection.xmin = pg_catalog.pg_current_xact_id()::xid
  ) THEN
    RAISE EXCEPTION 'reasoning-ledger superseding projection was not updated in the same transaction';
  END IF;
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION reasoning_ledger.freeze_schema_metadata()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'reasoning-ledger schema metadata is immutable';
  END IF;
  IF OLD.key = 'schema_version'
     AND OLD.value->>'catalog_signature' IS NULL
     AND NEW.key = OLD.key
     AND (NEW.value - 'catalog_signature') = (OLD.value - 'catalog_signature')
     AND NEW.value->>'catalog_signature' ~ '^[0-9a-f]{64}$' THEN
    RETURN NEW;
  END IF;
  RAISE EXCEPTION 'reasoning-ledger schema metadata is immutable';
END;
$$;

DROP TRIGGER IF EXISTS statement_immutable ON reasoning_ledger.statement;
CREATE TRIGGER statement_immutable
BEFORE UPDATE OR DELETE ON reasoning_ledger.statement
FOR EACH ROW EXECUTE FUNCTION reasoning_ledger.reject_authority_mutation();

DROP TRIGGER IF EXISTS project_anchor_immutable ON reasoning_ledger.project_anchor;
CREATE TRIGGER project_anchor_immutable
BEFORE UPDATE OR DELETE ON reasoning_ledger.project_anchor
FOR EACH ROW EXECUTE FUNCTION reasoning_ledger.reject_authority_mutation();

DROP TRIGGER IF EXISTS evidence_descriptor_immutable ON reasoning_ledger.evidence_descriptor;
CREATE TRIGGER evidence_descriptor_immutable
BEFORE UPDATE OR DELETE ON reasoning_ledger.evidence_descriptor
FOR EACH ROW EXECUTE FUNCTION reasoning_ledger.reject_authority_mutation();

DROP TRIGGER IF EXISTS statement_revision_immutable ON reasoning_ledger.statement_revision;
CREATE TRIGGER statement_revision_immutable
BEFORE UPDATE OR DELETE ON reasoning_ledger.statement_revision
FOR EACH ROW EXECUTE FUNCTION reasoning_ledger.reject_authority_mutation();

DROP TRIGGER IF EXISTS revision_transaction_bound ON reasoning_ledger.statement_revision;
CREATE CONSTRAINT TRIGGER revision_transaction_bound
AFTER INSERT ON reasoning_ledger.statement_revision
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION reasoning_ledger.validate_revision_transaction();

DROP TRIGGER IF EXISTS statement_revision_evidence_immutable ON reasoning_ledger.statement_revision_evidence;
CREATE TRIGGER statement_revision_evidence_immutable
BEFORE UPDATE OR DELETE ON reasoning_ledger.statement_revision_evidence
FOR EACH ROW EXECUTE FUNCTION reasoning_ledger.reject_authority_mutation();

DROP TRIGGER IF EXISTS relation_immutable ON reasoning_ledger.relation;
CREATE TRIGGER relation_immutable
BEFORE UPDATE OR DELETE ON reasoning_ledger.relation
FOR EACH ROW EXECUTE FUNCTION reasoning_ledger.reject_authority_mutation();

DROP TRIGGER IF EXISTS relation_evidence_immutable ON reasoning_ledger.relation_evidence;
CREATE TRIGGER relation_evidence_immutable
BEFORE UPDATE OR DELETE ON reasoning_ledger.relation_evidence
FOR EACH ROW EXECUTE FUNCTION reasoning_ledger.reject_authority_mutation();

DROP TRIGGER IF EXISTS ledger_event_immutable ON reasoning_ledger.ledger_event;
CREATE TRIGGER ledger_event_immutable
BEFORE UPDATE OR DELETE ON reasoning_ledger.ledger_event
FOR EACH ROW EXECUTE FUNCTION reasoning_ledger.reject_authority_mutation();

DROP TRIGGER IF EXISTS supersedes_event_transaction_bound ON reasoning_ledger.ledger_event;
CREATE CONSTRAINT TRIGGER supersedes_event_transaction_bound
AFTER INSERT ON reasoning_ledger.ledger_event
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION reasoning_ledger.validate_supersedes_event_transaction();

DROP TRIGGER IF EXISTS embedding_profile_immutable ON reasoning_ledger.embedding_profile;
CREATE TRIGGER embedding_profile_immutable
BEFORE UPDATE OR DELETE ON reasoning_ledger.embedding_profile
FOR EACH ROW EXECUTE FUNCTION reasoning_ledger.reject_authority_mutation();

DROP TRIGGER IF EXISTS current_projection_event_bound ON reasoning_ledger.current_projection;
CREATE TRIGGER current_projection_event_bound
BEFORE INSERT OR UPDATE OR DELETE ON reasoning_ledger.current_projection
FOR EACH ROW EXECUTE FUNCTION reasoning_ledger.validate_current_projection_event();

DROP TRIGGER IF EXISTS supersedes_transaction_bound ON reasoning_ledger.relation;
CREATE CONSTRAINT TRIGGER supersedes_transaction_bound
AFTER INSERT ON reasoning_ledger.relation
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION reasoning_ledger.validate_supersedes_transaction();

DROP TRIGGER IF EXISTS schema_metadata_immutable ON reasoning_ledger.schema_metadata;
CREATE TRIGGER schema_metadata_immutable
BEFORE UPDATE OR DELETE ON reasoning_ledger.schema_metadata
FOR EACH ROW EXECUTE FUNCTION reasoning_ledger.freeze_schema_metadata();

INSERT INTO reasoning_ledger.schema_metadata(key, value)
VALUES (
  'schema_version',
  jsonb_build_object(
    'name', 'reasoning_ledger',
    'version', 3,
    'embedding_dimensions', 1536,
    'authority_model', 'immutable_revision_event_projection',
    'contract_signature', 'a6416321fe6e8026e8e0fb29d39099c7aa2eecbe79d3ce357c7bf4c9a4ed64e4',
    'catalog_signature', NULL
  )
)
ON CONFLICT (key) DO NOTHING;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM reasoning_ledger.schema_metadata
    WHERE key = 'schema_version'
      AND (value - 'catalog_signature') = jsonb_build_object(
        'name', 'reasoning_ledger',
        'version', 3,
        'embedding_dimensions', 1536,
        'authority_model', 'immutable_revision_event_projection',
        'contract_signature', 'a6416321fe6e8026e8e0fb29d39099c7aa2eecbe79d3ce357c7bf4c9a4ed64e4'
      )
      AND (
        value->>'catalog_signature' IS NULL
        OR value->>'catalog_signature' ~ '^[0-9a-f]{64}$'
      )
  ) THEN
    RAISE EXCEPTION 'reasoning-ledger schema metadata differs from the configured authority contract';
  END IF;
END;
$$;

CREATE INDEX IF NOT EXISTS statement_revision_project_type_idx
ON reasoning_ledger.statement_revision(project_id, statement_type, created_at DESC);

CREATE INDEX IF NOT EXISTS statement_revision_scope_gin_idx
ON reasoning_ledger.statement_revision USING gin(scope);

CREATE INDEX IF NOT EXISTS statement_revision_search_gin_idx
ON reasoning_ledger.statement_revision USING gin(search_document);

CREATE INDEX IF NOT EXISTS relation_from_idx
ON reasoning_ledger.relation(project_id, from_statement_id, from_revision, relation_type);

CREATE INDEX IF NOT EXISTS relation_to_idx
ON reasoning_ledger.relation(project_id, to_statement_id, to_revision, relation_type);

CREATE INDEX IF NOT EXISTS ledger_event_aggregate_idx
ON reasoning_ledger.ledger_event(project_id, aggregate_kind, aggregate_id, event_id);

CREATE INDEX IF NOT EXISTS current_projection_validity_idx
ON reasoning_ledger.current_projection(project_id, validity, statement_id);
