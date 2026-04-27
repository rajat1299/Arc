# OpsCanvas API

FastAPI service boundary for OpsCanvas ingest and query APIs.

Implemented routes:

- `GET /healthz` returns service status metadata.
- `POST /v1/ingest/runs` validates one canonical `opscanvas-core` `Run` payload and
  stores it in process-local memory before returning an accepted envelope with span
  and event counts.
- `GET /v1/runs` returns run summaries sorted by `started_at` descending. It supports
  `status`, `runtime`, `tenant_id`, `environment`, and `limit` query filters.
- `GET /v1/runs/metrics` returns aggregate in-memory run counts, cost, tokens, and
  p95 latency for local development dashboards.
- `GET /v1/runs/{run_id}` returns the full canonical `Run`.
- `GET /v1/runs/{run_id}/spans` returns the canonical spans for a run.

The run store is process-local memory only. It does not write to a database, queue,
redaction pipeline, auth layer, or pricing engine. Submitting a duplicate run ID
replaces the prior in-memory run deliberately so local/dev ingestion can be retried
idempotently.

## Local Smoke

Start the API from the repository root:

```sh
uv run uvicorn opscanvas_api.app:app --app-dir services/api/src --reload
```

In another terminal, post a canonical sample run and query it back:

```sh
make smoke-ingest
```

The smoke fixture includes a root agent span, model calls, a tool call, and a
suboptimal retry span with usage, cost, structured input/output, attributes, and
events. It checks `/v1/runs`, `/v1/runs/{run_id}`, `/v1/runs/{run_id}/spans`, and
`/v1/runs/metrics`.

The smoke script targets `http://127.0.0.1:8000` by default. Override the API URL
or run ID with:

```sh
uv run python scripts/smoke_ingest.py --api-url http://127.0.0.1:8001 --run-id run_ui_fixture
```
