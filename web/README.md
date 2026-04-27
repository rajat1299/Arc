# Web

Minimal Next.js shell for the Arc/OpsCanvas trace operations workspace.

## Data Boundary

The shell reads `OPSCANVAS_API_BASE_URL` on the server and fetches
`/v1/runs` when it is set. The selected run comes from `?runId=<id>` when
present, falling back to the first returned run. For the selected run, the page
also fetches `/v1/runs/{run_id}`, `/v1/runs/{run_id}/spans`, and
`/v1/runs/metrics`.

Every API fetch has a bounded timeout and validates the returned shape before
rendering it. If the API is not configured, unavailable, returns an error, or
returns an unexpected payload shape, the affected page section falls back to the
static mock data from `web/app/data.ts` so the first screen remains usable.

## Local API Data

Start the API in one terminal:

```sh
uv run uvicorn opscanvas_api.app:app --app-dir services/api/src --reload
```

In another terminal, seed it with a sample run:

```sh
make smoke-ingest
```

Then start the web shell with the API base URL:

```sh
OPSCANVAS_API_BASE_URL=http://127.0.0.1:8000 pnpm --filter web dev
```

Leave `OPSCANVAS_API_BASE_URL` unset to exercise the static fallback behavior.

## Commands

- `pnpm --filter web dev`
- `pnpm --filter web build`
- `pnpm --filter web lint`
- `pnpm --filter web typecheck`
