# Web

Next.js shell for the OpsCanvas trace operations workspace. Server-rendered,
single-page, three-pane layout: runs, trace waterfall, span detail.

## Data Boundary

The shell reads `OPSCANVAS_API_BASE_URL` on the server and fetches:

- `GET /v1/runs` — run summaries for the table.
- `GET /v1/runs/metrics` — totals for the summary strip (counts, cost, tokens,
  p95 latency).
- `GET /v1/runs/{run_id}` — full canonical run, including spans, for the
  currently selected row.
- `GET /v1/runs/{run_id}/spans` — fetched in parallel with the run detail to
  populate the waterfall cheaply.

Selection is driven entirely by the URL:

- `?runId=<id>` — picks the run rendered in the trace pane. If absent, the page
  picks the most recent failed run, then suboptimal, then the first run.
- `?spanId=<id>` — picks the span rendered in the detail pane. If absent, the
  page picks the most recent failed span in the selected run, then any
  suboptimal/interrupted span, then the root span.

Every API fetch has a 1.5s timeout and validates the returned shape before
rendering. If the API is unset, unreachable, or returns an unexpected payload,
the page falls back to plausible mock operational data and the topbar shows a
`MOCK DATA` chip (or `API OFFLINE` plus a quiet inline error if the base URL
was set but unreachable). The page never blanks out.

### API auth

If the API has `OPSCANVAS_API_AUTH_ENABLED=true`, set `OPSCANVAS_API_KEY` on
the **server side** (i.e. exported in the env that runs `pnpm dev` / `next
build`). The shell forwards it as `Authorization: Bearer <key>` on every
upstream request. Leave it unset when auth is disabled.

## Local API Data

Start the API in one terminal:

```sh
uv run --with uvicorn --package opscanvas-api python -m uvicorn opscanvas_api.app:app --app-dir services/api/src --host 127.0.0.1 --port 8000 --reload
```

In another terminal, seed it with the canonical 5-span fixture:

```sh
uv run python scripts/smoke_ingest.py --run-id run_ui_fixture
```

Then start the web shell with the API base URL:

```sh
OPSCANVAS_API_BASE_URL=http://127.0.0.1:8000 pnpm --filter web dev
```

Open `http://localhost:3000/?runId=run_ui_fixture`. The topbar will show a
`LIVE` chip and the host. Stop the API and refresh to see the chip flip to
`API OFFLINE` with mock data underneath.

Leave `OPSCANVAS_API_BASE_URL` unset to exercise the static fallback path,
which renders a synthetic set of runs covering failed, suboptimal, running,
and succeeded states.

## Commands

- `pnpm --filter web dev`
- `pnpm --filter web build`
- `pnpm --filter web lint`
- `pnpm --filter web typecheck`
