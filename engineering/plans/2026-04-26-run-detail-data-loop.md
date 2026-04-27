# Run Detail Data Loop Implementation Plan

> **For implementers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development where code behavior is introduced. Every implementation task must commit its initial work before review, then commit any review fixes separately. Report all commit SHAs.

**Goal:** Make the trace-ops web shell consume real API run detail, spans, and aggregate metrics while preserving a resilient mock fallback.

**Architecture:** The API already stores canonical runs in process memory. This slice adds lightweight query contracts for aggregate run metrics and ensures the web data boundary fetches `/v1/runs`, selected run detail, selected spans, and metrics with bounded fallbacks. The web shell remains server-rendered, static-data safe, and design-aligned.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, pytest, Next.js 15, React 19, TypeScript, pnpm.

**Reference Docs:** Local-only docs live at `/Users/rajattiwari/mycelium 2/opscanvas/docs/`. Workers must read or receive relevant excerpts from `ENGINEERING.md`, `DESIGN.md`, and `RESEARCH_AND_REUSE_GUIDE.md`. Do not commit local-only docs or design screenshots.

---

## Execution Rules

- Work in `/Users/rajattiwari/.config/superpowers/worktrees/Arc/run-detail-data-loop` unless told otherwise.
- Do not touch `/Users/rajattiwari/mycelium 2/opscanvas/docs`; it is ignored local reference material.
- Do not copy competitor code or screenshots. Use the research guide only for product/design patterns.
- Keep each task scoped to its listed files.
- Stage only files owned by the task. Do not stage unrelated working tree changes.
- Commit after initial implementation and after each review-fix round.
- Run the listed verification commands before each commit.

## Task 1: API Run Metrics Query Contract

**Purpose:** Add one small aggregate endpoint that gives the web shell real cost/status/token metrics from the in-memory run store.

**Files:**
- Modify: `services/api/src/opscanvas_api/routes/runs.py`
- Modify: `services/api/tests/test_runs.py`
- Modify: `services/api/README.md`

**API Requirements:**
- Add `GET /v1/runs/metrics`.
- The route must be declared before `/{run_id}` so it is not captured as a run ID.
- Response model should include at minimum:
  - `run_count`
  - `failed_count`
  - `running_count`
  - `suboptimal_count`
  - `total_cost_usd`
  - `total_tokens`
  - `p95_latency_ms`
- Metrics should derive from the current in-memory runs.
- `p95_latency_ms` should be `null` if no completed run has both `started_at` and `ended_at`.
- Keep it simple: no database, auth, background workers, pricing engine, or persisted rollups.
- Tests should cover empty-store metrics and metrics after ingesting multiple runs with mixed statuses, usage, and durations.

**Verification Commands:**
- `uv run pytest services/api/tests packages/opscanvas-core/tests -q`
- `uv run ruff check services/api packages/opscanvas-core`
- `uv run mypy services/api/src packages/opscanvas-core/src`

**Expected Result:** The API exposes stable local-dev aggregate metrics for the web shell.

## Task 2: Web Fetch Real Run Detail And Spans

**Purpose:** Replace static span/detail data with API-backed selected run detail and spans when the API is configured.

**Files:**
- Modify: `web/app/data.ts`
- Modify: `web/app/page.tsx`
- Modify: `web/README.md`

**Data Requirements:**
- Add API types for canonical `Run`, `Span`, `Usage`, and span events sufficient for the UI.
- Continue fetching `/v1/runs` for run summaries.
- Select the active run from a `runId` search param when present; otherwise use the first returned run summary.
- Fetch `/v1/runs/{run_id}` and `/v1/runs/{run_id}/spans` for the active run.
- Fetch `/v1/runs/metrics` for summary metrics.
- Every fetch must have a bounded timeout and safe fallback.
- If any detail/span/metrics fetch fails or returns malformed data, fall back only for that part where practical. The full page must still render.
- Preserve current fallback behavior when `OPSCANVAS_API_BASE_URL` is absent.
- Do not add client-side state management or a data fetching library.

**UI Requirements:**
- Run table rows should link to `?runId=<id>` and visually indicate the selected run.
- Span tree/waterfall should render API spans when available.
- Right-side span detail should reflect selected/API span data rather than fixed mock content where practical.
- Summary strip should render API metrics when available.
- Preserve design constraints: dark default, dense shell, semantic run table, no marketing copy, no decorative gradients/orbs, no screenshot assets.

**Verification Commands:**
- `pnpm --filter web lint`
- `pnpm --filter web typecheck`
- `pnpm --filter web build`
- If feasible, local page load with no API, unavailable API, and a temporary `/v1/runs` + detail/spans/metrics server.

**Expected Result:** The web shell can display real run summaries, selected run spans, and aggregate metrics from the API while remaining resilient.

## Task 3: Richer Smoke Fixture For UI Data

**Purpose:** Make the smoke-ingested sample representative enough to drive the run detail page.

**Files:**
- Modify: `scripts/smoke_ingest.py`
- Modify: `README.md`
- Modify: `services/api/README.md`
- Modify: `web/README.md`

**Requirements:**
- The sample run should include a realistic span tree:
  - root agent span
  - model call span
  - tool call span
  - failed or suboptimal span with an event/attribute explaining the failure
  - final model call span
- Include usage/cost values at run and span level so metrics and span costs are visible.
- Include span `input`, `output`, and attributes in JSON-compatible form.
- Smoke script should still POST, list, and detail-query the run.
- Add an optional `--run-id` argument for deterministic UI testing.
- Print the web URL to open, e.g. `http://localhost:3000/?runId=<id>`, after success.
- Keep exit behavior strict and nonzero on failed requests.

**Verification Commands:**
- `uv run python scripts/smoke_ingest.py --help`
- `uv run pytest services/api/tests packages/opscanvas-core/tests packages/opscanvas-agents/tests -q`
- `make verify`
- Optional live API smoke.

**Expected Result:** A developer can seed one realistic trace and immediately view it in the web shell.

## Task 4: Final Integration Review

**Purpose:** Confirm the run-detail data loop is coherent and merge-ready.

**Files:**
- Modify as needed after review only.

**Review Checklist:**
- All code is committed on `run-detail-data-loop`.
- `make verify` passes.
- `pnpm --filter web build` passes.
- `docker compose -f infra/docker-compose.dev.yml config` passes.
- Live API smoke passes if local port is available.
- Web fallback still renders without API.
- Web can render API-backed run summaries/detail/spans/metrics when provided.
- No local-only docs or screenshot assets are committed.

**Expected Result:** Branch is ready to merge into `main` as the next implementation slice.
