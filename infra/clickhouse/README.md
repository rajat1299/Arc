# ClickHouse

ClickHouse is the local analytical store for high-volume OpsCanvas runtime data.
It owns wide tables for runs, spans, span events, and scores so trace search,
span-tree views, latency rollups, and cost dashboards can scan efficiently.

The initial local migration is intentionally plain SQL:

```bash
docker compose -f infra/docker-compose.dev.yml up clickhouse
```

`001_runs_spans_events.sql` is mounted read-only into the ClickHouse container
and runs during first database initialization. Delete the `clickhouse_data`
Docker volume to re-run it from scratch in local development.

Design notes:

- `runs`, `spans`, and `span_events` map to the canonical `Run`, `Span`,
  `SpanEvent`, `Usage`, `RunStatus`, and `SpanKind` contracts.
- IDs emitted by runtime translators are stored as `String`; org, project,
  environment, and eval dataset IDs are UUIDs because they come from Postgres.
- Inputs, outputs, metadata, attributes, and score comments are stored as JSON
  strings for this seed. Compression and a typed JSON/Object strategy can be
  revisited after ingestion and query workloads are real.
- Runtime-specific provider, model, tool, and service-tier fields are promoted
  only where they are expected to drive common filters, cost grouping, or
  pricing edge cases. Everything else stays in `attributes_json`.
- Token and cost rollups include first-class cache, reasoning, audio, service
  tier, and batch multiplier fields so the future cost engine can persist the
  edge cases called out in the storage/cost spike.
- This is not a production migration system. It is a reviewable schema seed for
  local development before persistence code exists.
