# OpenAI-Compatible Proxy V0 Implementation Plan

> **For subagents:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Use superpowers:test-driven-development for behavior changes. Commit after your task and after any review fixes.

**Goal:** Add the first tier-3 proxy path so an OpenAI Chat Completions client can point its `base_url` at OpsCanvas, receive the upstream response unchanged, and get a canonical OpsCanvas run stored automatically.

**Architecture:** Add a narrow FastAPI proxy router for non-streaming `POST /v1/chat/completions`. The client authenticates to OpsCanvas with the existing bearer API-key auth. OpsCanvas owns the upstream OpenAI API key server-side, forwards a sanitized request to a configured upstream base URL, returns the upstream response body/status to the caller, and records one canonical `Run` with one `model_call` span. Request/response capture is summary-only by default; no raw prompts, completions, or secrets are persisted.

**Tech Stack:** Python 3.12, FastAPI, httpx, Pydantic settings, existing `opscanvas-core` contracts/pricing/redaction, pytest with `httpx.MockTransport`, Ruff, mypy.

---

## Context

Product and engineering docs are local-only and gitignored in the main checkout. Subagents must read or be passed this context:

- Product thesis: proxy mode is the tier-3 onboarding hook. It should let users change one OpenAI SDK base URL and see traces without adopting a native runtime plugin.
- Existing API auth uses `Authorization: Bearer <OpsCanvas API key>` in `services/api/src/opscanvas_api/auth.py`. Do not try to forward the caller's `Authorization` header as an OpenAI key in v0; it conflicts with OpsCanvas auth.
- Server-owned upstream credentials are the v0 security model:
  - Client `OPENAI_API_KEY` should be an OpsCanvas API key when calling the proxy.
  - Server config `OPSCANVAS_API_OPENAI_UPSTREAM_API_KEY` is the OpenAI key used upstream.
- Existing app wiring lives in `services/api/src/opscanvas_api/app.py`.
- Existing store protocol lives in `services/api/src/opscanvas_api/store.py`; use `RunStore.upsert(run)`.
- Existing route dependency for store lives in `services/api/src/opscanvas_api/routes/runs.py`.
- Existing canonical contracts live in `packages/opscanvas-core/src/opscanvas_core/events.py`.
- Existing pricing fallback in `services/api/src/opscanvas_api/routes/runs.py` computes costs from `SpanKind.model_call` spans with attributes `provider` and `model`.
- Official OpenAI docs verified on 2026-04-28:
  - REST API uses bearer auth.
  - Chat Completions remains `POST /v1/chat/completions`.
  - Responses is the newer recommended API.
  - Streaming uses SSE and Chat Completions usage may only arrive in the final usage chunk, which may be missing if interrupted.

## Non-Goals

- No streaming/SSE proxy in v0.
- No Responses API proxy in v0.
- No client BYOK passthrough.
- No arbitrary upstream URLs per request.
- No raw prompt or completion persistence by default.
- No tool-call/replay/eval generation.
- No budget enforcement or rate limiting.
- No web UI changes.
- No ClickHouse schema changes.

---

## Proxy Semantics

- Route: `POST /v1/chat/completions`
- Disabled by default unless `OPSCANVAS_API_OPENAI_PROXY_ENABLED=true`.
- When disabled, return `404` so the API surface is not accidentally advertised.
- When enabled without `OPSCANVAS_API_OPENAI_UPSTREAM_API_KEY`, return `503`.
- When request JSON includes `"stream": true`, return `400` with a clear v0 non-streaming message.
- Forward request JSON to `{OPSCANVAS_API_OPENAI_UPSTREAM_BASE_URL}/chat/completions`.
- Default upstream base URL: `https://api.openai.com/v1`.
- Only `https` upstream base URLs are allowed by default. Allow `http://127.0.0.1`, `http://localhost`, and `http://testserver` for tests/local dev only if needed.
- Return the upstream status code and body to the caller unchanged for success and provider errors.
- Forward only safe response headers such as:
  - `content-type`
  - `x-request-id`
  - `openai-organization`
  - `openai-processing-ms`
  - `openai-version`
  - `x-ratelimit-*`
- Drop hop-by-hop, cookie, auth, and transfer headers.

## Header Semantics

Forward only safe request headers:

- `content-type`
- `accept`
- `openai-organization`
- `openai-project`
- `idempotency-key`
- `x-request-id`
- `x-client-request-id`

Never forward:

- `authorization`
- `cookie`
- `set-cookie`
- `host`
- `connection`
- `content-length`
- `transfer-encoding`
- `x-opscanvas-*`

Inject upstream auth server-side:

```text
Authorization: Bearer {settings.openai_upstream_api_key}
```

## Canonical Run Mapping

For each proxied non-streaming request, create one `Run`:

- `runtime = "openai-compatible-proxy"`
- `status = succeeded` for upstream 2xx, otherwise `failed`
- `workflow_name = "openai.chat.completions.create"`
- `started_at` / `ended_at` around the upstream request
- `metadata` includes:
  - `provider = "openai"`
  - `model`
  - `proxy.upstream_path = "/chat/completions"`
  - `proxy.upstream_status_code`
  - upstream request IDs when available

Create one child `Span`:

- `kind = SpanKind.model_call`
- `name = "openai.chat.completions.create"`
- `attributes` include:
  - `provider = "openai"`
  - `model`
  - `http.status_code`
  - `upstream_path = "/chat/completions"`
  - `openai.response_id` when present
  - `service_tier` when present
- `usage` maps OpenAI usage:
  - `prompt_tokens -> input_tokens`
  - `completion_tokens -> output_tokens`
  - `prompt_tokens_details.cached_tokens -> cached_input_tokens`
  - `completion_tokens_details.reasoning_tokens -> reasoning_tokens`
  - `total_tokens -> total_tokens`
- `input` is summary-only:
  - model, message count, tool count, stream flag, temperature/top_p presence, metadata key count
- `output` is summary-only:
  - response id, model, choices count, finish reasons, usage-present flag

Do not persist raw `messages`, `input`, `content`, completion text, tool arguments, Authorization values, or upstream API keys.

---

### Task 1: Settings, Dependency, And App Protection

**Files:**
- Modify: `services/api/pyproject.toml`
- Modify: `services/api/src/opscanvas_api/settings.py`
- Modify: `services/api/src/opscanvas_api/app.py`
- Modify: `services/api/tests/test_auth_routes.py`
- Create: `services/api/tests/test_openai_proxy_settings.py`

**Requirements:**
- Add `httpx>=0.28.0` as a runtime dependency of `opscanvas-api`.
- Add settings:
  - `openai_proxy_enabled: bool = False`
  - `openai_upstream_base_url: str = "https://api.openai.com/v1"`
  - `openai_upstream_api_key: str = Field(default="", repr=False)`
  - `openai_proxy_timeout_seconds: float = 120.0`
  - `proxy_capture_body: Literal["none", "summary", "redacted"] = "summary"`
- Protect `/v1/chat/completions` with the existing pre-body auth guard when auth is enabled.
- Add a placeholder router or route only if needed for tests; full proxy implementation is Task 3.
- Tests:
  - default settings keep proxy disabled.
  - env settings load proxy fields.
  - auth-enabled `/v1/chat/completions` with malformed body and missing/invalid bearer returns `401` before JSON body parse.
  - `/healthz` remains public.
- Do not change existing ingest/runs behavior.

**Verification:**
- `uv run pytest services/api/tests/test_openai_proxy_settings.py services/api/tests/test_auth_routes.py -q`
- `uv run ruff check services/api`
- `uv run mypy services/api/src`

**Commit:** `Add OpenAI proxy settings scaffold`

---

### Task 2: Pure Proxy Helpers

**Files:**
- Create: `services/api/src/opscanvas_api/openai_proxy.py`
- Create: `services/api/tests/test_openai_proxy_helpers.py`

**Requirements:**
- Implement pure, network-free helpers:
  - `build_upstream_url(base_url: str, path: str) -> str`
  - `validate_upstream_base_url(base_url: str) -> None`
  - `forward_request_headers(headers: Mapping[str, str], upstream_api_key: str) -> dict[str, str]`
  - `forward_response_headers(headers: Mapping[str, str]) -> dict[str, str]`
  - `usage_from_openai(payload: Mapping[str, object]) -> Usage | None`
  - `summarize_chat_request(payload: Mapping[str, object]) -> JsonValue`
  - `summarize_chat_response(payload: Mapping[str, object]) -> JsonValue`
  - `build_proxy_run(...) -> Run`
- Generate prefixed canonical IDs using existing ID helpers where practical.
- `build_proxy_run` must create one run and one model span using the mapping above.
- Keep summaries bounded and safe. Do not store raw `messages[*].content`, tool arguments, completion `message.content`, or authorization data.
- Tests must cover:
  - URL join and validation.
  - request header filtering/injected upstream auth.
  - response header filtering.
  - usage mapping including cached and reasoning token details.
  - canonical run/span status/metadata/usage.
  - prompt/completion/API key secrets absent from serialized run JSON.

**Verification:**
- `uv run pytest services/api/tests/test_openai_proxy_helpers.py -q`
- `uv run ruff check services/api/src/opscanvas_api/openai_proxy.py services/api/tests/test_openai_proxy_helpers.py`
- `uv run mypy services/api/src`

**Commit:** `Add OpenAI proxy mapping helpers`

---

### Task 3: Chat Completions Proxy Route

**Files:**
- Create: `services/api/src/opscanvas_api/routes/openai_proxy.py`
- Modify: `services/api/src/opscanvas_api/app.py`
- Create: `services/api/tests/test_openai_proxy_route.py`

**Requirements:**
- Add router for `POST /v1/chat/completions`.
- When proxy disabled, return `404`.
- When enabled without upstream key, return `503`.
- Parse JSON only after auth has passed through the existing pre-body guard.
- Reject non-object JSON with `422`.
- Reject `"stream": true` with `400` and a v0 message.
- Forward non-streaming JSON to upstream with `httpx.AsyncClient` or injectable app-state test seam.
- Test seam:
  - Allow tests to inject a mocked async transport/client through `app.state` or dependency override.
  - No real network in tests.
- Return upstream response body/status and safe response headers to the caller.
- Store a canonical run in `RunStore` for both successful upstream 2xx and upstream non-2xx responses.
- If upstream transport raises, store a failed run when enough request context exists, then return `502` with a sanitized error.
- Tests must cover:
  - disabled proxy `404`.
  - missing upstream key `503`.
  - stream true `400`.
  - success forwards sanitized headers and server-side upstream auth.
  - success stores one run/span with usage, provider/model, and no raw prompt/completion.
  - upstream provider error body/status returned and failed run stored.
  - transport error returns `502`, failed run stored, no secret leakage.

**Verification:**
- `uv run pytest services/api/tests/test_openai_proxy_route.py -q`
- `uv run ruff check services/api`
- `uv run mypy services/api/src`

**Commit:** `Add OpenAI chat completions proxy route`

---

### Task 4: Auth, Cost, And Smoke Coverage

**Files:**
- Modify: `services/api/tests/test_auth_routes.py`
- Modify: `services/api/tests/test_runs.py`
- Create or modify: `scripts/smoke_openai_proxy.py`

**Requirements:**
- Extend auth route tests:
  - auth enabled + malformed body + no proxy bearer returns `401` before parse.
  - auth enabled + valid OpsCanvas bearer reaches proxy route behavior.
- Add cost test:
  - proxied run with priced OpenAI model and usage produces non-null `RunSummary.cost_usd` through existing pricing fallback.
- Add smoke script:
  - `scripts/smoke_openai_proxy.py --help` works.
  - accepts `--api-url`, `--api-key`, `--model`, `--prompt`.
  - posts to `/v1/chat/completions` using OpenAI-compatible payload.
  - queries `/v1/runs?runtime=openai-compatible-proxy&limit=1`.
  - documents that it requires API auth when enabled and a server-side upstream key.
  - keep default dry/no-network safe? If the script actually calls proxy, it should be explicit that API must be configured.
- Do not require a live OpenAI call in automated tests.

**Verification:**
- `uv run pytest services/api/tests/test_auth_routes.py services/api/tests/test_runs.py services/api/tests/test_openai_proxy_route.py -q`
- `uv run python scripts/smoke_openai_proxy.py --help`
- `uv run ruff check services/api scripts/smoke_openai_proxy.py`
- `uv run mypy services/api/src`

**Commit:** `Add OpenAI proxy auth and smoke coverage`

---

### Task 5: Docs And Final Verification

**Files:**
- Modify: `README.md`
- Modify: `services/api/README.md`
- Create: `engineering/openai-proxy-v0-report.md`

**Requirements:**
- Document OpenAI-compatible proxy v0:
  - enable with `OPSCANVAS_API_OPENAI_PROXY_ENABLED=true`.
  - configure `OPSCANVAS_API_OPENAI_UPSTREAM_API_KEY`.
  - client uses OpsCanvas API key as `OPENAI_API_KEY`.
  - client base URL points to OpsCanvas `/v1`.
  - only non-streaming Chat Completions in v0.
  - no raw prompt/completion persistence by default.
  - no client BYOK passthrough.
  - no Responses API or SSE streaming yet.
- Include Python OpenAI SDK example.
- Report should summarize architecture, routes, settings, security posture, mapping, tests, and remaining risks.
- Final verification:
  - `make verify`
  - `pnpm --filter web build`
  - `uv run python scripts/smoke_openai_proxy.py --help`
  - `docker compose -f infra/docker-compose.dev.yml config`

**Commit:** `Document OpenAI proxy v0`

---
