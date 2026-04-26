-- OpsCanvas local-dev Postgres metadata schema.
-- Postgres stores relational state: org/project/environment hierarchy, API key
-- hashes, budget policies, eval datasets, and prompt versions. Runtime event
-- data belongs in ClickHouse; Redis is only a queue/cache/rate-limit placeholder.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS orgs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE orgs IS 'Top-level tenant boundary for logical isolation.';
COMMENT ON COLUMN orgs.metadata IS 'Org metadata and future auth-provider attributes; not runtime trace payloads.';

CREATE TABLE IF NOT EXISTS projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    slug TEXT NOT NULL,
    name TEXT NOT NULL,
    capture_inputs BOOLEAN NOT NULL DEFAULT true,
    capture_outputs BOOLEAN NOT NULL DEFAULT true,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, slug)
);

COMMENT ON TABLE projects IS 'Project-level metadata for grouping runs, budget policies, eval datasets, and prompts.';
COMMENT ON COLUMN projects.capture_inputs IS 'Data-minimization control used before storing Span.input in ClickHouse.';
COMMENT ON COLUMN projects.capture_outputs IS 'Data-minimization control used before storing Span.output in ClickHouse.';

CREATE TABLE IF NOT EXISTS environments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    slug TEXT NOT NULL,
    name TEXT NOT NULL,
    is_production BOOLEAN NOT NULL DEFAULT false,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (project_id, slug)
);

COMMENT ON TABLE environments IS 'Environment dimension for production/staging/dev filtering and policy scope.';
COMMENT ON COLUMN environments.slug IS 'Stable environment key expected to align with Run.environment values.';

CREATE TABLE IF NOT EXISTS api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    environment_id UUID REFERENCES environments(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    key_hash TEXT NOT NULL UNIQUE,
    prefix TEXT NOT NULL,
    scopes TEXT[] NOT NULL DEFAULT ARRAY['ingest']::TEXT[],
    last_used_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE api_keys IS 'API key records for local auth scaffolding. Raw keys are never stored.';
COMMENT ON COLUMN api_keys.key_hash IS 'Hash of the API key only; never persist raw API keys.';
COMMENT ON COLUMN api_keys.prefix IS 'Non-secret display prefix used for key identification in UI and logs.';

CREATE TABLE IF NOT EXISTS budget_policies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    environment_id UUID REFERENCES environments(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    scope TEXT NOT NULL CHECK (scope IN ('org', 'project', 'environment', 'tenant')),
    tenant_id TEXT,
    monthly_cap_usd NUMERIC(18, 6),
    per_run_cap_usd NUMERIC(18, 6),
    per_tenant_monthly_cap_usd NUMERIC(18, 6),
    action TEXT NOT NULL DEFAULT 'alert' CHECK (action IN ('alert', 'hard_stop', 'model_downshift')),
    is_enabled BOOLEAN NOT NULL DEFAULT true,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (
        monthly_cap_usd IS NOT NULL
        OR per_run_cap_usd IS NOT NULL
        OR per_tenant_monthly_cap_usd IS NOT NULL
    )
);

COMMENT ON TABLE budget_policies IS 'Budget policy state evaluated by the future budget engine against ClickHouse cost rollups.';
COMMENT ON COLUMN budget_policies.tenant_id IS 'Optional runtime tenant key matching Run.tenant_id for tenant-scoped caps.';
COMMENT ON COLUMN budget_policies.action IS 'Tier-1 plugins may hard-stop; tier-2/tier-3 ingestion should alert only until enforcement exists.';

CREATE TABLE IF NOT EXISTS eval_datasets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    environment_id UUID REFERENCES environments(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    schema_version TEXT NOT NULL DEFAULT '0.1',
    criteria JSONB NOT NULL DEFAULT '{}'::jsonb,
    item_count INTEGER NOT NULL DEFAULT 0 CHECK (item_count >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (project_id, name)
);

COMMENT ON TABLE eval_datasets IS 'Eval dataset metadata and criteria. Dataset items/cassettes are intentionally out of scope for this seed.';
COMMENT ON COLUMN eval_datasets.schema_version IS 'Persisted eval dataset format version following the shared schema-versioning policy.';
COMMENT ON COLUMN eval_datasets.criteria IS 'Judge criteria, assertions, thresholds, or rubric metadata as JSONB.';

CREATE TABLE IF NOT EXISTS prompt_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    environment_id UUID REFERENCES environments(id) ON DELETE SET NULL,
    prompt_key TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version > 0),
    content TEXT NOT NULL,
    config JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    archived_at TIMESTAMPTZ,
    UNIQUE (project_id, prompt_key, version)
);

COMMENT ON TABLE prompt_versions IS 'Versioned prompt state for replay/eval workflows. Runtime prompt usage still lands on spans.';
COMMENT ON COLUMN prompt_versions.config IS 'Prompt runtime configuration such as model, temperature, tools, or provider-specific settings.';

CREATE INDEX IF NOT EXISTS projects_org_id_idx ON projects (org_id);
CREATE INDEX IF NOT EXISTS environments_project_id_idx ON environments (project_id);
CREATE INDEX IF NOT EXISTS api_keys_org_id_idx ON api_keys (org_id);
CREATE INDEX IF NOT EXISTS budget_policies_org_scope_idx ON budget_policies (org_id, scope);
CREATE INDEX IF NOT EXISTS eval_datasets_project_id_idx ON eval_datasets (project_id);
CREATE INDEX IF NOT EXISTS prompt_versions_project_key_idx ON prompt_versions (project_id, prompt_key);
