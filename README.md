# Arc

Engineering home for the Arc surface in the OpsCanvas -> Arc -> Atrium stack.

This repository is currently a foundation scaffold for shared OpsCanvas/Arc
tooling. It provides the monorepo layout, deterministic Python commands, a local
in-memory ingest/query API with optional ClickHouse persistence, and a minimal web
shell with API fallback behavior.

## Layout

- `packages/opscanvas-core/`: shared Python contracts for canonical runs, spans, events, and schema versions.
- `packages/opscanvas-agents/`: OpenAI Agents SDK tracing processor, exporter, and ingest client.
- `services/api/`: FastAPI service with memory and local ClickHouse ingest/query stores.
- `web/`: Next.js shell that reads API run summaries when configured and falls back to static data.
- `infra/`: placeholder for future local development infrastructure.

## Local Docs Policy

Local `docs/` is gitignored here. Keep product and engineering specs in that
directory on your machine or share them out of band. Do not commit local-only
reference docs to this repository.

## First Commands

Install and verify the workspace:

```sh
uv sync --all-packages
pnpm install
make verify
```

Useful focused commands:

```sh
uv run --with uvicorn --package opscanvas-api python -m uvicorn opscanvas_api.app:app --app-dir services/api/src --host 127.0.0.1 --port 8000 --reload
make smoke-ingest
pnpm --filter web dev
uv run pytest packages/opscanvas-core/tests -q
uv run ruff check .
uv run mypy packages/opscanvas-core/src
pnpm run verify
```

## Local Ingest Smoke

Start the API in one terminal:

```sh
uv run --with uvicorn --package opscanvas-api python -m uvicorn opscanvas_api.app:app --app-dir services/api/src --host 127.0.0.1 --port 8000 --reload
```

Then post and query a canonical sample run:

```sh
make smoke-ingest
```

The smoke script posts a richer run-detail fixture with agent, model, tool, and
retry spans, then checks list, detail, spans, and metrics routes. It defaults to
`http://127.0.0.1:8000`. Use a deterministic run ID when testing the web shell:

```sh
uv run python scripts/smoke_ingest.py --run-id run_ui_fixture
```

Use `--api-url http://127.0.0.1:8001` when the API is on a different port.
On success, the script prints the web URL to open with `?runId=<id>`.

## ClickHouse API Mode

Memory mode is the default and does not require Docker. To run the API with the
local ClickHouse store, start ClickHouse first:

```sh
docker compose -f infra/docker-compose.dev.yml up -d clickhouse
```

Then start the API with the ClickHouse backend:

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

The default smoke command still works and does not require changing flags:

```sh
make smoke-ingest
```

To prove data survives an API process restart, leave the Docker ClickHouse
service running and run the ClickHouse persistence smoke. The script starts the
API on an isolated port, ingests the rich fixture, queries list/detail/spans and
metrics, restarts the API process, then queries the same run again:

```sh
uv run python scripts/smoke_clickhouse_persistence.py
```

Use `--port 18081` if the default smoke port is already occupied. The script
fails rather than reusing an existing API process.

Existing ClickHouse dev volumes created before the `runs.environment` column was
added will not be updated by `CREATE TABLE IF NOT EXISTS`. Recreate dev volumes:

```sh
docker compose -f infra/docker-compose.dev.yml down -v
docker compose -f infra/docker-compose.dev.yml up -d clickhouse
```

or run the migration manually:

```sh
docker compose -f infra/docker-compose.dev.yml exec clickhouse clickhouse-client --user opscanvas --password opscanvas_dev_password --database opscanvas --query "ALTER TABLE runs ADD COLUMN IF NOT EXISTS environment Nullable(String) AFTER environment_id"
```

Start the web shell separately:

```sh
pnpm --filter web dev
```

By default the web shell uses static fallback data. To point it at the local API,
set `OPSCANVAS_API_BASE_URL` before starting Next.js:

```sh
OPSCANVAS_API_BASE_URL=http://127.0.0.1:8000 pnpm --filter web dev
```

## Repository

- Remote: <https://github.com/rajat1299/Arc>
