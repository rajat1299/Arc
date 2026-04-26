-- OpsCanvas local-dev ClickHouse schema.
-- ClickHouse stores the wide analytical shape: runs, spans, span events, and scores.
-- Canonical fields mirror opscanvas_core Run, Span, SpanEvent, Usage, RunStatus,
-- and SpanKind. Runtime-specific fields stay in *_json or provider/model/tool columns
-- so the canonical contract can remain stable across SDK integrations.

CREATE DATABASE IF NOT EXISTS opscanvas;

USE opscanvas;

CREATE TABLE IF NOT EXISTS runs
(
    org_id Nullable(UUID) COMMENT 'Metadata hierarchy id from Postgres. Nullable while early local ingest can run without auth.',
    project_id Nullable(UUID) COMMENT 'Metadata hierarchy id from Postgres. Mirrors Run.project_id when that value is UUID-backed.',
    environment_id Nullable(UUID) COMMENT 'Environment id from Postgres for production/staging/dev rollups.',
    run_id String COMMENT 'Canonical Run.id. Kept as String because runtime translators may emit non-UUID ids.',
    schema_version LowCardinality(String) COMMENT 'Canonical persisted Run schema version, for example 0.1.',
    runtime LowCardinality(String) COMMENT 'Canonical Run.runtime such as openai-agents-python, claude-agent-sdk, langgraph, or crewai.',
    status LowCardinality(String) COMMENT 'Canonical RunStatus: succeeded, failed, interrupted, suboptimal, or running.',
    started_at DateTime64(3, 'UTC') COMMENT 'Canonical Run.started_at.',
    ended_at Nullable(DateTime64(3, 'UTC')) COMMENT 'Canonical Run.ended_at.',
    duration_ms Nullable(UInt64) COMMENT 'Runtime or ingest-computed latency rollup for the full run.',
    input_tokens Nullable(UInt64) COMMENT 'Usage.input_tokens rollup for the run.',
    output_tokens Nullable(UInt64) COMMENT 'Usage.output_tokens rollup for the run.',
    cached_input_tokens Nullable(UInt64) COMMENT 'Usage.cached_input_tokens rollup for cache-aware pricing.',
    reasoning_tokens Nullable(UInt64) COMMENT 'Usage.reasoning_tokens rollup when a provider exposes reasoning token counts.',
    total_tokens Nullable(UInt64) COMMENT 'Usage.total_tokens rollup.',
    cost_usd Nullable(Decimal(18, 9)) COMMENT 'Usage.cost_usd rollup as computed by the cost engine.',
    tenant_id Nullable(String) COMMENT 'Canonical Run.tenant_id for customer tenant rollups and budget policies.',
    user_id Nullable(String) COMMENT 'Canonical Run.user_id for end-user rollups after edge redaction.',
    workflow_name Nullable(String) COMMENT 'Canonical Run.workflow_name for agent/workflow reporting.',
    metadata_json String COMMENT 'Canonical Run.metadata serialized as JSON after edge redaction.',
    runtime_attributes_json String COMMENT 'Runtime-specific run attributes that are useful for debugging but not part of the canonical contract.',
    inserted_at DateTime64(3, 'UTC') DEFAULT now64(3) COMMENT 'Storage ingestion time, not a runtime timestamp.'
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(started_at)
ORDER BY (started_at, run_id);

CREATE TABLE IF NOT EXISTS spans
(
    org_id Nullable(UUID) COMMENT 'Copied from the owning run for tenant-pruned analytical scans.',
    project_id Nullable(UUID) COMMENT 'Copied from the owning run for project-level trace and cost dashboards.',
    environment_id Nullable(UUID) COMMENT 'Copied from the owning run for environment-level filtering.',
    run_id String COMMENT 'Canonical Span.run_id and foreign key by convention to runs.run_id.',
    span_id String COMMENT 'Canonical Span.id. Kept as String for runtime translator compatibility.',
    parent_span_id Nullable(String) COMMENT 'Canonical Span.parent_id for reconstructing the agent-aware span tree.',
    kind LowCardinality(String) COMMENT 'Canonical SpanKind: agent, model_call, tool_call, handoff, guardrail, mcp_list, sandbox_op, retry, or custom.',
    name String COMMENT 'Canonical Span.name.',
    started_at DateTime64(3, 'UTC') COMMENT 'Canonical Span.started_at.',
    ended_at Nullable(DateTime64(3, 'UTC')) COMMENT 'Canonical Span.ended_at.',
    duration_ms Nullable(UInt64) COMMENT 'Runtime or ingest-computed span latency.',
    input_tokens Nullable(UInt64) COMMENT 'Usage.input_tokens for this span.',
    output_tokens Nullable(UInt64) COMMENT 'Usage.output_tokens for this span.',
    cached_input_tokens Nullable(UInt64) COMMENT 'Usage.cached_input_tokens for this span.',
    reasoning_tokens Nullable(UInt64) COMMENT 'Usage.reasoning_tokens for this span.',
    total_tokens Nullable(UInt64) COMMENT 'Usage.total_tokens for this span.',
    cost_usd Nullable(Decimal(18, 9)) COMMENT 'Usage.cost_usd for this span as computed by the cost engine.',
    input_json String COMMENT 'Canonical Span.input serialized as redacted JSON. String keeps large structured payloads simple for local dev; compression can be tuned after workloads are real.',
    output_json String COMMENT 'Canonical Span.output serialized as redacted JSON. Capture can be disabled per project later; compression can be tuned after workloads are real.',
    attributes_json String COMMENT 'Canonical Span.attributes serialized as JSON; runtime-specific extras live here unless promoted.',
    runtime LowCardinality(String) COMMENT 'Runtime source for this span, repeated for query speed.',
    provider Nullable(String) COMMENT 'Runtime-specific provider such as openai, anthropic, bedrock, vertex, or local.',
    model Nullable(String) COMMENT 'Runtime-specific model name for model_call spans and cost grouping.',
    tool_name Nullable(String) COMMENT 'Runtime-specific tool/function name for tool_call spans.',
    service_tier Nullable(String) COMMENT 'Runtime-specific provider tier used by pricing edge cases.',
    inserted_at DateTime64(3, 'UTC') DEFAULT now64(3) COMMENT 'Storage ingestion time, not a runtime timestamp.'
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(started_at)
ORDER BY (run_id, started_at, span_id);

CREATE TABLE IF NOT EXISTS span_events
(
    org_id Nullable(UUID) COMMENT 'Copied from the owning run for tenant-pruned analytical scans.',
    project_id Nullable(UUID) COMMENT 'Copied from the owning run for project-level trace queries.',
    environment_id Nullable(UUID) COMMENT 'Copied from the owning run for environment filtering.',
    run_id String COMMENT 'Owning canonical Run.id.',
    span_id String COMMENT 'Canonical SpanEvent.span_id and foreign key by convention to spans.span_id.',
    event_id String COMMENT 'Canonical SpanEvent.id.',
    name String COMMENT 'Canonical SpanEvent.name, for example token.delta, approval.requested, retry.scheduled.',
    timestamp DateTime64(3, 'UTC') COMMENT 'Canonical SpanEvent.timestamp.',
    attributes_json String COMMENT 'Canonical SpanEvent.attributes serialized as JSON after edge redaction.',
    inserted_at DateTime64(3, 'UTC') DEFAULT now64(3) COMMENT 'Storage ingestion time, not a runtime timestamp.'
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(timestamp)
ORDER BY (run_id, span_id, timestamp, event_id);

CREATE TABLE IF NOT EXISTS scores
(
    org_id Nullable(UUID) COMMENT 'Copied from metadata state for tenant-pruned eval and quality scans.',
    project_id Nullable(UUID) COMMENT 'Copied from metadata state for project-level eval reporting.',
    environment_id Nullable(UUID) COMMENT 'Optional environment associated with the scored run or dataset.',
    run_id Nullable(String) COMMENT 'Canonical Run.id when the score applies to a run.',
    span_id Nullable(String) COMMENT 'Canonical Span.id when the score applies to a span.',
    eval_dataset_id Nullable(UUID) COMMENT 'Postgres eval_datasets.id when score comes from an eval run.',
    score_name String COMMENT 'Stable score key such as correctness, helpfulness, latency_ok, or budget_ok.',
    score_value Nullable(Float64) COMMENT 'Numeric score when available. Boolean/pass-fail scores can use 1 and 0.',
    score_comment String COMMENT 'Human or judge explanation for the score.',
    score_source LowCardinality(String) COMMENT 'Score producer such as human, judge_llm, policy, or system.',
    attributes_json String COMMENT 'Runtime/eval-specific score details that are not canonical score fields.',
    inserted_at DateTime64(3, 'UTC') DEFAULT now64(3) COMMENT 'Storage ingestion time.'
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(inserted_at)
ORDER BY (inserted_at, score_name);
