# Pricing V0 Report

## Summary

Pricing v0 adds deterministic, offline model-cost computation for local API cost
surfaces without changing canonical ingestion payloads. The source of truth is
`opscanvas_core.pricing`, a static catalog snapshotted on 2026-04-27 with source
URLs attached to seeded entries.

## Behavior

- Runtime-reported run `usage.cost_usd` is authoritative. API summaries and
  metrics use it before any computed value.
- When run `usage.cost_usd` is missing, `GET /v1/runs` and
  `GET /v1/runs/metrics` compute a read-time fallback from priced model-call
  spans.
- Span fallback reads provider from span attribute `provider` and model from
  `model` or `agent.model`. For OpenAI Agents runtimes, the API can infer
  provider `openai` when the span provider is missing.
- If no span can be priced, the API can compute from run metadata `provider` and
  `model` plus run usage.
- Unknown providers or models return no computed cost. Run summary cost remains
  `None`; aggregate metrics treat the missing cost as `0`.
- Pricing never guesses or fakes prices for unknown models.

## Seeded Catalog

Catalog prices are USD per 1 million tokens.

Seeded OpenAI models:

- `gpt-5.5`
- `gpt-5.4`
- `gpt-5.4-mini`

Seeded Anthropic models:

- `claude-opus-4.7`
- `claude-opus-4.6`
- `claude-opus-4.5`
- `claude-opus-4.1`
- `claude-opus-4`
- `claude-sonnet-4.6`
- `claude-sonnet-4.5`
- `claude-sonnet-4`
- `claude-sonnet-3.7`
- `claude-haiku-4.5`
- `claude-haiku-3.5`
- `claude-haiku-3`

Seeded Google models:

- `gemini-3-flash-preview`
- `gemini-2.5-pro`
- `gemini-2.5-flash`
- `gemini-2.5-flash-lite`

Source URLs:

- OpenAI: <https://openai.com/api/pricing/>
- Anthropic: <https://platform.claude.com/docs/en/about-claude/pricing>
- Google Gemini: <https://ai.google.dev/gemini-api/docs/pricing>

## Non-Goals

Pricing v0 intentionally does not include live provider or OpenRouter sync,
admin catalog editing, organization-specific discounts, enterprise agreements,
taxes, regional premiums, batch discounts, fast-mode premiums, budget
enforcement, alerting, or billing integration.

## Handoff Notes

Update `packages/opscanvas-core/src/opscanvas_core/pricing.py` when seeded prices
or aliases change. Keep new entries source-backed and deterministic, add focused
tests for new provider/model behavior, and preserve the current precedence rule:
reported run cost first, computed fallback second, unknown models unpriced.

## Concise Final Report

Task 3 documents pricing v0 as a static/offline, source-backed catalog. The docs
now explain that runtime-reported `usage.cost_usd` wins, missing costs are
computed at read time from priced model spans or run metadata, OpenAI Agents spans
can infer provider `openai`, and unknown models stay unpriced with aggregate cost
treated as zero. Seeded OpenAI, Anthropic, and Google models plus source URLs and
explicit non-goals are captured for implementation handoff.
