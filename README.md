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

## Pricing V0

Pricing v0 is a static, offline, source-backed model-price catalog in
`opscanvas_core.pricing`. It does not call provider APIs, OpenRouter, or any live
sync job at runtime. Catalog prices are USD per 1 million tokens, snapshotted on
2026-04-27, and the module keeps source URLs on the seeded catalog entries.

Seeded providers and models:

- OpenAI: `gpt-5.5`, `gpt-5.4`, `gpt-5.4-mini`
- Anthropic: `claude-opus-4.7`, `claude-opus-4.6`, `claude-opus-4.5`,
  `claude-opus-4.1`, `claude-opus-4`, `claude-sonnet-4.6`,
  `claude-sonnet-4.5`, `claude-sonnet-4`, `claude-sonnet-3.7`,
  `claude-haiku-4.5`, `claude-haiku-3.5`, `claude-haiku-3`
- Google: `gemini-3-flash-preview`, `gemini-2.5-pro`,
  `gemini-2.5-flash`, `gemini-2.5-flash-lite`

Source URLs:

- OpenAI: <https://openai.com/api/pricing/>
- Anthropic: <https://platform.claude.com/docs/en/about-claude/pricing>
- Google Gemini: <https://ai.google.dev/gemini-api/docs/pricing>

Run cost semantics are intentionally conservative. A runtime-reported
`usage.cost_usd` on the run is authoritative and wins. When it is missing, the
API list and metrics routes compute a read-time fallback from priced model-call
spans. Model spans use span attributes `provider` and `model` or `agent.model`;
for OpenAI Agents runtimes, the API can infer provider `openai` when the span
omits provider. If no span can be priced, the API can fall back to run metadata
`provider` and `model` with run usage.

Unknown providers or models are never guessed. A run summary cost remains `None`
when no reported or computed cost exists, and aggregate metrics treat that run as
`0` so totals stay deterministic without fake prices.

Non-goals for pricing v0: live price sync, organization discounts, enterprise
agreements, taxes, regional premiums, batch discounts, fast-mode premiums, budget
enforcement, and billing integration.

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

## API Auth V0

API-key auth is disabled by default for local development. To exercise the v0
auth scaffold locally, start the API with one or more environment-configured
bearer keys:

```sh
OPSCANVAS_API_AUTH_ENABLED=true \
OPSCANVAS_API_API_KEYS=dev_key_... \
uv run --with uvicorn --package opscanvas-api python -m uvicorn opscanvas_api.app:app --app-dir services/api/src --host 127.0.0.1 --port 8000 --reload
```

Then run the smoke script with the same key:

```sh
uv run python scripts/smoke_ingest.py --api-key dev_key_...
```

Auth v0 is a local/dev scaffold for bearer API keys configured through the API
environment. `/healthz` remains public. `/v1/ingest` and `/v1/runs` routes are
protected only when auth is enabled.

Auth v0 does not include an org, project, or user database; RBAC; UI management;
key rotation; or rate limits. It is a scaffold for authenticated local and dev
deployments, not a production auth system.

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
