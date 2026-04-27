# ClickHouse Persistence Implementation Plan

> **For implementers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development where code behavior is introduced. Every implementation task must commit its initial work before review, then commit any review fixes separately. Report all commit SHAs.

**Goal:** Add a selectable ClickHouse-backed run store so local API data can survive process restarts while preserving the current in-memory default.

**Architecture:** Keep the existing `RunStore` protocol as the route boundary. Add serialization helpers that flatten canonical `Run`, `Span`, and `SpanEvent` objects into the existing ClickHouse schema, then add a `ClickHouseRunStore` adapter selected by API settings. The first slice should remain synchronous and simple; no queue, auth, pricing engine, Postgres org resolution, or Redis cache yet.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, ClickHouse, `clickhouse-connect`, pytest, Ruff, mypy, Docker Compose.

**Reference Docs:** Local-only docs live at `/Users/rajattiwari/mycelium 2/opscanvas/docs/`. Workers must read or receive relevant excerpts from `ENGINEERING.md`, `SDK_REUSE.md`, and `RESEARCH_AND_REUSE_GUIDE.md`. Do not commit local-only docs or screenshots.

---

## Execution Rules

- Work in `/Users/rajattiwari/.config/superpowers/worktrees/Arc/clickhouse-persistence`.
- Do not touch `/Users/rajattiwari/mycelium 2/opscanvas/docs`; it is ignored local reference material.
- Do not copy competitor code. Use the research guide only for architecture and product patterns.
- Keep each task scoped to its listed files.
- Stage only files owned by the task. Do not stage unrelated working tree changes.
- Commit after initial implementation and after each review-fix round.
- Run the listed verification commands before each commit.

## Non-Goals For This Branch

- No auth, API-key validation, org/project lookup, Postgres metadata writes, or Redis queues.
- No pricing computation. Persist `usage.cost_usd` if provided, but do not invent prices.
- No async ingestion pipeline or background worker.
- No schema rewrite unless a blocker is found in the already shipped ClickHouse DDL.
- No web UI redesign.

## Task 1: Store Serialization Layer

**Purpose:** Isolate the mechanical mapping between canonical contracts and ClickHouse rows so the database adapter is small and testable.

**Files:**
- Create: `services/api/src/opscanvas_api/storage.py`
- Create: `services/api/tests/test_storage.py`

**Requirements:**
- Add pure functions to convert a canonical `Run` into row dictionaries for:
  - `runs`
  - `spans`
  - `span_events`
- Preserve JSON aliases: span `input` should serialize from `input_data`, and `output` from `output_data`.
- Serialize metadata, runtime attributes, span input/output, span attributes, and event attributes as deterministic JSON strings.
- Compute `duration_ms` for run/span rows when `ended_at` is present and not before `started_at`; otherwise `None`.
- Map usage fields conservatively: missing usage fields become `None`, not `0`.
- Extract useful runtime fields from span attributes when present:
  - provider from `provider`
  - model from `model` or `agent.model`
  - tool name from `tool`, `tool.name`, or span name for `tool_call`
  - service tier from `service_tier` or `service.tier`
- Keep org/project/environment UUID columns `None` for now unless values are valid UUID strings.
- Tests should cover a rich run with spans/events/usage/input/output/attributes and a running run with missing `ended_at`.

**Verification Commands:**
- `uv run pytest services/api/tests/test_storage.py -q`
- `uv run ruff check services/api/src/opscanvas_api/storage.py services/api/tests/test_storage.py`
- `uv run mypy services/api/src`

**Expected Result:** Storage mapping is deterministic, covered by unit tests, and independent of ClickHouse connectivity.

## Task 2: ClickHouse RunStore Adapter

**Purpose:** Implement the `RunStore` protocol against ClickHouse using the shipped `runs`, `spans`, and `span_events` tables.

**Files:**
- Modify: `services/api/pyproject.toml`
- Modify: `uv.lock`
- Modify: `services/api/src/opscanvas_api/store.py`
- Create: `services/api/tests/test_clickhouse_store.py`

**Requirements:**
- Add the official Python ClickHouse client dependency, preferring `clickhouse-connect`.
- Implement `ClickHouseRunStore` with the same methods as `InMemoryRunStore`:
  - `upsert(run: Run) -> None`
  - `get(run_id: str) -> Run | None`
  - `list(...filters...) -> list[Run]`
- For local-dev idempotency, replacing an existing run ID must not duplicate query results. Prefer `ALTER TABLE ... DELETE` before insert for the matching `run_id` across `span_events`, `spans`, and `runs`, followed by inserts. This is acceptable for local/dev only.
- `get()` must reconstruct a canonical `Run` with its spans and span events from ClickHouse rows.
- `list()` must apply the same filters and newest-first ordering as the memory store.
- Keep tests network-free by using a fake ClickHouse client object that records inserts/queries and returns representative rows. Do not require Docker in unit tests.
- Keep integration with real Docker ClickHouse for the final branch smoke, not the unit-test path.

**Verification Commands:**
- `uv run pytest services/api/tests/test_clickhouse_store.py services/api/tests/test_storage.py -q`
- `uv run ruff check services/api`
- `uv run mypy services/api/src`

**Expected Result:** A ClickHouse-backed store can round-trip canonical runs through rows while preserving the existing route contract.

## Task 3: API Store Selection And Docs

**Purpose:** Let developers select memory or ClickHouse storage through environment settings without changing route code.

**Files:**
- Modify: `services/api/src/opscanvas_api/settings.py`
- Modify: `services/api/src/opscanvas_api/app.py`
- Modify: `services/api/tests/test_ingest.py`
- Modify: `services/api/tests/test_runs.py`
- Modify: `services/api/README.md`
- Modify: `README.md`

**Requirements:**
- Add settings with `OPSCANVAS_API_` prefix:
  - `STORE_BACKEND`, default `memory`, accepted values `memory` and `clickhouse`
  - `CLICKHOUSE_HOST`, default `127.0.0.1`
  - `CLICKHOUSE_PORT`, default `8123`
  - `CLICKHOUSE_USERNAME`, default `opscanvas`
  - `CLICKHOUSE_PASSWORD`, default `opscanvas_dev_password`
  - `CLICKHOUSE_DATABASE`, default `opscanvas`
  - `CLICKHOUSE_SECURE`, default `false`
- `create_app()` should select `InMemoryRunStore` by default and `ClickHouseRunStore` when configured.
- Tests must prove the default is memory and that clickhouse selection constructs the ClickHouse store without requiring a real network call.
- Update docs with the exact Docker Compose and API startup commands for ClickHouse mode.
- Keep memory mode as the default in all existing tests.

**Verification Commands:**
- `uv run pytest services/api/tests -q`
- `uv run ruff check services/api`
- `uv run mypy services/api/src`
- `make verify`

**Expected Result:** The API can be started in memory mode or ClickHouse mode through environment variables, with no route changes.

## Task 4: Live ClickHouse Smoke

**Purpose:** Prove the end-to-end local persistence path against the Docker ClickHouse service.

**Files:**
- Modify: `scripts/smoke_ingest.py`
- Modify: `README.md`
- Modify: `services/api/README.md`

**Requirements:**
- Add optional smoke guidance or flags only if needed; do not make the default smoke require ClickHouse.
- Start the API in ClickHouse mode against `infra/docker-compose.dev.yml`.
- Ingest the rich fixture, query list/detail/spans/metrics, restart or recreate the API process, then query the same run again to prove process restart persistence.
- If automating restart inside the script is too much for this branch, add a small `scripts/smoke_clickhouse_persistence.py` that assumes ClickHouse is running and manages only API process lifecycle.
- Keep failure behavior strict and nonzero.

**Verification Commands:**
- `docker compose -f infra/docker-compose.dev.yml config`
- `uv run python scripts/smoke_ingest.py --help`
- `make verify`
- Live ClickHouse persistence smoke with Docker if local ports are available.

**Expected Result:** A developer can run local infra, start the API in ClickHouse mode, seed the demo run, and still query it after an API restart.

## Task 5: Final Integration Review

**Purpose:** Confirm the ClickHouse persistence slice is coherent and merge-ready.

**Files:**
- Modify as needed after review only.

**Review Checklist:**
- All code is committed on `clickhouse-persistence`.
- `make verify` passes.
- `pnpm --filter web build` passes.
- `docker compose -f infra/docker-compose.dev.yml config` passes.
- Memory-mode smoke still passes.
- ClickHouse-mode live persistence smoke passes, or any local Docker blocker is explicitly documented.
- No local-only docs or screenshot assets are committed.
- `main` local dirty README/DESIGN work remains untouched.

**Expected Result:** Branch is ready to merge into `main` as the persistence slice.
