# Runtime Plugin Contract

OpsCanvas runtime plugins translate SDK-specific execution into the canonical
OpsCanvas contract. Every plugin emits `Run`, `Span`, `SpanEvent`, and `Usage`
objects from `opscanvas-core`, serialized with `model_dump(mode="json",
by_alias=True)` for ingestion. The canonical output contract is fixed across
runtimes; only the capture architecture varies by SDK.

Plugins should use public runtime APIs only. Do not depend on private modules,
private callback managers, undocumented persistence internals, or object shapes
that an SDK does not commit to supporting. Keep optional runtime dependencies
optional at package import time: importing an OpsCanvas plugin must work without
the target runtime installed, and runtime-specific failures should include clear
install instructions.

Capture should be minimal and non-invasive. Prefer wrappers, processors,
callbacks, and streaming surfaces over persistence hooks or monkeypatching for
v0 integrations. A plugin may buffer spans in memory while a run is active, but
it should export exactly one completed canonical run for a traced operation and
respect exporter shutdown.

Plugins should redact or summarize high-risk raw inputs and outputs by default.
Avoid unbounded state dumps, secrets, credential material, full prompts from
unknown sources, and large tool payloads unless a caller has explicitly opted
into that behavior. Metadata should explain runtime-specific events without
changing the shared schema.

Network export is optional. When enabled, plugins post completed canonical runs
to `/v1/ingest/runs` and include bearer authorization only when configured.
