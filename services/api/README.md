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

The run store defaults to process-local memory. Set
`OPSCANVAS_API_STORE_BACKEND=clickhouse` to use the local ClickHouse adapter instead.
The API does not yet write to a queue, redaction pipeline, auth layer, or pricing
engine. Submitting a duplicate run ID replaces the prior run deliberately so
local/dev ingestion can be retried idempotently.

## Local Smoke

Start the API from the repository root:

```sh
uv run --with uvicorn --package opscanvas-api python -m uvicorn opscanvas_api.app:app --app-dir services/api/src --host 127.0.0.1 --port 8000 --reload
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

## ClickHouse Mode

Start the local ClickHouse service from the repository root:

```sh
docker compose -f infra/docker-compose.dev.yml up -d clickhouse
```

Then start the API with the ClickHouse backend selected:

```sh
OPSCANVAS_API_STORE_BACKEND=clickhouse \
OPSCANVAS_API_CLICKHOUSE_HOST=127.0.0.1 \
OPSCANVAS_API_CLICKHOUSE_PORT=8123 \
OPSCANVAS_API_CLICKHOUSE_USERNAME=opscanvas \
OPSCANVAS_API_CLICKHOUSE_PASSWORD=opscanvas_dev_password \
OPSCANVAS_API_CLICKHOUSE_DATABASE=opscanvas \
OPSCANVAS_API_CLICKHOUSE_SECURE=false \
uv run --with uvicorn --package opscanvas-api python -m uvicorn opscanvas_api.app:app --app-dir services/api/src --host 127.0.0.1 --port 8000 --reload
```

The default smoke remains unchanged and can be run against either backend:

```sh
make smoke-ingest
```

To exercise the full local persistence path, leave Docker ClickHouse running and
run the restart smoke from the repository root:

```sh
uv run python scripts/smoke_clickhouse_persistence.py
```

The persistence smoke starts the API in ClickHouse mode on `127.0.0.1:18080`,
ingests the rich fixture, checks list/detail/spans/metrics, restarts the API
process, and checks the same run again. Pass `--port 18081` or another free port
if needed; the script refuses to attach to an already-running API.

If your local ClickHouse volume was created before the `runs.environment` column was
added, either recreate the dev volume:

```sh
docker compose -f infra/docker-compose.dev.yml down -v
docker compose -f infra/docker-compose.dev.yml up -d clickhouse
```

or patch the existing table:

```sh
docker compose -f infra/docker-compose.dev.yml exec clickhouse clickhouse-client --user opscanvas --password opscanvas_dev_password --database opscanvas --query "ALTER TABLE runs ADD COLUMN IF NOT EXISTS environment Nullable(String) AFTER environment_id"
```
