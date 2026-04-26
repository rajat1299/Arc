# OpsCanvas API

FastAPI service boundary for OpsCanvas ingest and query APIs.

Implemented routes:

- `GET /healthz` returns service status metadata.
- `POST /v1/ingest/runs` validates one canonical `opscanvas-core` `Run` payload and
  stores it in process-local memory before returning an accepted envelope with span
  and event counts.
- `GET /v1/runs` returns run summaries sorted by `started_at` descending. It supports
  `status`, `runtime`, `tenant_id`, `environment`, and `limit` query filters.
- `GET /v1/runs/{run_id}` returns the full canonical `Run`.
- `GET /v1/runs/{run_id}/spans` returns the canonical spans for a run.

The run store is process-local memory only. It does not write to a database, queue,
redaction pipeline, auth layer, or pricing engine. Submitting a duplicate run ID
replaces the prior in-memory run deliberately so local/dev ingestion can be retried
idempotently.
