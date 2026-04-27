# Auth API Key V0 Implementation Plan

> **For implementers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development where code behavior is introduced. Every implementation task must commit its initial work before review, then commit any review fixes separately. Report all commit SHAs.

**Goal:** Add a conservative bearer API-key authentication scaffold for API ingest/query routes while preserving unauthenticated local development by default.

**Architecture:** Keep auth as a small FastAPI dependency in `opscanvas_api.auth`, configured through existing `Settings` with the `OPSCANVAS_API_` prefix. `/healthz` remains public. `/v1/ingest/*` and `/v1/runs*` require `Authorization: Bearer <key>` only when auth is enabled. API keys are configured from local/dev environment variables for v0; there is no database-backed key management yet.

**Tech Stack:** Python 3.12, FastAPI dependencies, Pydantic Settings, pytest, Ruff, mypy, stdlib `secrets.compare_digest`.

**Reference Docs:** Local-only docs live at `/Users/rajattiwari/mycelium 2/opscanvas/docs/`. Workers must read or receive relevant excerpts from `ENGINEERING.md`, `SDK_REUSE.md`, and `RESEARCH_AND_REUSE_GUIDE.md`. Do not commit local-only docs or screenshots.

---

## Execution Rules

- Work in `/Users/rajattiwari/.config/superpowers/worktrees/Arc/auth-api-key-v0`.
- Do not touch `/Users/rajattiwari/mycelium 2/opscanvas/docs`; it is ignored local reference material.
- Keep auth disabled by default for local development and existing tests.
- Stage only files owned by the task. Do not stage unrelated working tree changes.
- Commit after initial implementation and after each review-fix round.
- Run the listed verification commands before each commit.

## Non-Goals For This Branch

- No org/project/user database model.
- No API-key creation UI, rotation UI, or admin console.
- No hashed key persistence or Postgres-backed key lookup.
- No RBAC, per-route scopes, tenant resolution, or audit log table.
- No OAuth/OIDC/JWT/session auth.
- No rate limiting or budget enforcement.
- No web UI changes.

## Auth Semantics

- New settings:
  - `OPSCANVAS_API_AUTH_ENABLED`, default `false`
  - `OPSCANVAS_API_API_KEYS`, default empty string, comma/newline separated for local/dev keys
- Auth disabled:
  - `/healthz`, `/v1/ingest/runs`, `/v1/runs`, `/v1/runs/{id}`, `/v1/runs/{id}/spans`, and `/v1/runs/metrics` behave exactly as today.
- Auth enabled:
  - `/healthz` stays public.
  - `/v1/ingest/*` and `/v1/runs*` require `Authorization: Bearer <key>`.
  - Missing/invalid/malformed bearer credentials return `401` with `WWW-Authenticate: Bearer`.
  - Auth enabled with no configured keys fails closed with `503` on protected routes.
  - Key comparison uses `secrets.compare_digest`.
- Auth dependency must not log or echo configured secrets.

## Task 1: Auth Helper Module

**Purpose:** Add isolated parsing and verification helpers that can be tested without route wiring.

**Files:**
- Create: `services/api/src/opscanvas_api/auth.py`
- Create: `services/api/tests/test_auth.py`

**Requirements:**
- Add an immutable `ApiKeyPrincipal` type with a non-secret `key_id` derived from the key value for debugging/test assertions. Use a short SHA-256 prefix or similar; never expose the full secret.
- Add `configured_api_keys(settings: Settings) -> tuple[str, ...]` that splits `settings.api_keys` by comma and newline, strips whitespace, and drops empty values.
- Add `validate_api_key(token: str, configured_keys: tuple[str, ...]) -> bool` using `secrets.compare_digest`.
- Add `authenticate_api_key(token: str, settings: Settings) -> ApiKeyPrincipal | None` for pure validation.
- Add a FastAPI dependency `require_api_key(...)` that:
  - returns `None` when auth is disabled
  - returns `ApiKeyPrincipal` when enabled and valid
  - raises `HTTPException(401)` with `WWW-Authenticate: Bearer` for missing/malformed/invalid bearer tokens
  - raises `HTTPException(503)` if auth is enabled but no keys are configured
- Tests must cover parsing comma/newline key strings, constant-time validation behavior via functional assertions, disabled auth no-op, valid bearer success, missing bearer, malformed scheme, invalid token, and enabled-with-empty-keys failure.

**Verification Commands:**
- `uv run pytest services/api/tests/test_auth.py -q`
- `uv run ruff check services/api/src/opscanvas_api/auth.py services/api/tests/test_auth.py`
- `uv run mypy services/api/src`

**Expected Result:** Auth behavior is testable and does not require route wiring yet.

## Task 2: Settings And Route Protection

**Purpose:** Wire auth settings and dependency into protected API routes without breaking local default behavior.

**Files:**
- Modify: `services/api/src/opscanvas_api/settings.py`
- Modify: `services/api/src/opscanvas_api/routes/ingest.py`
- Modify: `services/api/src/opscanvas_api/routes/runs.py`
- Modify: `services/api/tests/test_ingest.py`
- Modify: `services/api/tests/test_runs.py`
- Create or modify if useful: `services/api/tests/test_auth_routes.py`

**Requirements:**
- Add settings fields:
  - `auth_enabled: bool = False`
  - `api_keys: str = ""`
- Protect the ingest and runs routers with `Depends(require_api_key)`.
- Do not protect `/healthz`.
- Existing memory-mode tests must clear `OPSCANVAS_API_AUTH_ENABLED` and `OPSCANVAS_API_API_KEYS` so ambient env cannot accidentally force auth.
- Tests must prove:
  - existing unauthenticated ingest/query behavior still works by default.
  - auth-enabled ingest rejects missing and invalid bearer credentials.
  - auth-enabled ingest accepts a configured key.
  - auth-enabled run list/detail/spans/metrics reject missing credentials and accept configured key.
  - `/healthz` stays public when auth is enabled.
  - auth enabled with empty keys fails closed with `503`.
- Do not change response models or canonical run contracts.

**Verification Commands:**
- `uv run pytest services/api/tests/test_auth.py services/api/tests/test_auth_routes.py services/api/tests/test_ingest.py services/api/tests/test_runs.py -q`
- `uv run ruff check services/api`
- `uv run mypy packages/opscanvas-core/src services/api/src`

**Expected Result:** API auth can be enabled by env for protected routes while current local dev and tests remain unauthenticated by default.

## Task 3: Smoke Script And Docs

**Purpose:** Make authenticated local smoke easy and document v0 auth boundaries.

**Files:**
- Modify: `scripts/smoke_ingest.py`
- Modify: `README.md`
- Modify: `services/api/README.md`

**Requirements:**
- Add optional `--api-key` to `scripts/smoke_ingest.py`.
- When `--api-key` is provided, send `Authorization: Bearer <api-key>` on all smoke requests.
- Default smoke behavior must remain unchanged and unauthenticated.
- Document how to start the API with auth enabled:
  - `OPSCANVAS_API_AUTH_ENABLED=true`
  - `OPSCANVAS_API_API_KEYS=dev_key_...`
- Document how to run smoke with `--api-key`.
- Document what auth v0 is and is not:
  - local/dev env-configured bearer keys
  - `/healthz` public
  - protected `/v1/ingest` and `/v1/runs`
  - no org/project/user DB, no RBAC, no UI, no rotation, no rate limits
- Do not add production claims beyond scaffold/dev deployment readiness.

**Verification Commands:**
- `uv run python scripts/smoke_ingest.py --help`
- `make verify`

**Expected Result:** A developer can enable API-key auth locally and run the existing smoke with a bearer token.

## Task 4: Final Integration Review

**Purpose:** Confirm the auth scaffold is coherent and merge-ready.

**Files:**
- Modify as needed after review only.

**Review Checklist:**
- All code is committed on `auth-api-key-v0`.
- `uv run mypy services/api/src` passes.
- `make verify` passes.
- `pnpm --filter web build` passes.
- `uv run python scripts/smoke_ingest.py --help` passes.
- Memory-mode smoke still passes without auth.
- Auth-enabled memory-mode smoke passes with `--api-key`.
- Missing auth returns `401` for protected routes when enabled.
- No local-only docs or screenshot assets are committed.
- Main worktree local README/DESIGN changes remain untouched.

**Expected Result:** Branch is ready to merge into `main` and push as the auth scaffold slice.
