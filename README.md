# Arc

Engineering home for the Arc surface in the OpsCanvas -> Arc -> Atrium stack.

This repository is currently a foundation scaffold for shared OpsCanvas/Arc
tooling. It provides the monorepo layout, deterministic Python commands, a local
in-memory ingest/query API, and a minimal web shell with API fallback behavior.

## Layout

- `packages/opscanvas-core/`: shared Python contracts for canonical runs, spans, events, and schema versions.
- `packages/opscanvas-agents/`: OpenAI Agents SDK tracing processor, exporter, and ingest client.
- `services/api/`: FastAPI service with local in-memory ingest and run query routes.
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
uv run uvicorn opscanvas_api.app:app --app-dir services/api/src --reload
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
uv run uvicorn opscanvas_api.app:app --app-dir services/api/src --reload
```

Then post and query a canonical sample run:

```sh
make smoke-ingest
```

The smoke script defaults to `http://127.0.0.1:8000`. Use
`uv run python scripts/smoke_ingest.py --api-url http://127.0.0.1:8001` when the
API is on a different port.

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
