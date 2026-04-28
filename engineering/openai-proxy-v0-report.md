# OpenAI-Compatible Proxy V0 Report

## Summary

OpenAI-compatible proxy v0 adds an opt-in FastAPI path that lets an OpenAI Chat
Completions client point its base URL at OpsCanvas, receive the upstream response
body/status, and get a canonical OpsCanvas run recorded automatically. The proxy
is intentionally narrow: non-streaming Chat Completions only, server-owned
upstream credentials only, and summary-only capture by default.

## Architecture

- The proxy route lives in the API service and forwards `POST /v1/chat/completions`
  to `{OPSCANVAS_API_OPENAI_UPSTREAM_BASE_URL}/chat/completions`.
- The default upstream base URL is `https://api.openai.com/v1`.
- Request and response header forwarding is allowlist-based. The route injects
  upstream authorization from server settings.
- Pure helper functions build the upstream URL, sanitize headers, summarize
  payloads, map usage, and create canonical runs.
- The existing `RunStore.upsert(run)` path records the generated canonical run.

## Route And Settings

- `OPSCANVAS_API_OPENAI_PROXY_ENABLED=false` by default. Disabled proxy requests
  return `404`.
- `OPSCANVAS_API_OPENAI_UPSTREAM_API_KEY` must be configured when the proxy is
  enabled, or requests return `503`.
- `OPSCANVAS_API_OPENAI_UPSTREAM_BASE_URL` is optional and defaults to
  `https://api.openai.com/v1`.
- `OPSCANVAS_API_OPENAI_PROXY_TIMEOUT_SECONDS` controls upstream timeout.
- `OPSCANVAS_API_PROXY_CAPTURE_BODY` defaults to `summary`.
- `stream: true` requests return `400` because SSE streaming is not part of v0.

## Auth And Security Posture

- Clients authenticate to OpsCanvas with the existing bearer API-key auth when
  `OPSCANVAS_API_AUTH_ENABLED=true`.
- In that mode, OpenAI SDK clients set `OPENAI_API_KEY` to an OpsCanvas API key
  and set `base_url` to the OpsCanvas API `/v1`.
- Caller `Authorization`, cookies, host, transfer, content length, and
  `x-opscanvas-*` request headers are not forwarded upstream.
- The proxy does not support client BYOK passthrough in v0. The upstream OpenAI
  key stays server-side.
- Raw prompts, completions, tool arguments, bearer tokens, and upstream API keys
  are not persisted by the default summary capture path.

## Canonical Run And Span Mapping

Each proxied non-streaming request creates one `Run`:

- `runtime`: `openai-compatible-proxy`
- `workflow_name`: `openai.chat.completions.create`
- `status`: `succeeded` for upstream 2xx, otherwise `failed`
- metadata: provider `openai`, model, upstream path/status, and safe upstream
  request ID when present

Each run contains one `model_call` span:

- `name`: `openai.chat.completions.create`
- attributes: provider, model, HTTP status, upstream path, response ID, service
  tier, and safe upstream request ID when present
- usage maps OpenAI `prompt_tokens`, `completion_tokens`,
  `prompt_tokens_details.cached_tokens`,
  `completion_tokens_details.reasoning_tokens`, and `total_tokens`
- input/output are summaries only: model, counts, flags, finish reasons,
  response ID, and usage presence

## Pricing Integration

Proxy runs use the existing pricing v0 fallback path. The generated model-call
span includes provider `openai`, model, and usage, so `GET /v1/runs` and
`GET /v1/runs/metrics` can compute `RunSummary.cost_usd` when the model exists in
the static pricing catalog. Unknown models remain unpriced.

## Tests And Verification

Implemented coverage includes settings defaults/env loading, auth-before-body
behavior, pure helper mapping, route behavior, upstream error handling, transport
error handling, smoke script help, and run summary pricing for proxied runs.

Task 5 verification:

- `uv run python scripts/smoke_openai_proxy.py --help`
- `git diff --check`

The live smoke command is documented but was not run for this task because it
would call an upstream provider.

## Remaining Risks And Non-Goals

- No Responses API proxy in v0.
- No SSE streaming or streamed usage capture.
- No client BYOK passthrough or per-request upstream URL selection.
- No budget enforcement, rate limiting, replay, eval generation, or UI changes.
- Upstream provider behavior, model availability, and pricing catalog freshness
  remain external concerns.
