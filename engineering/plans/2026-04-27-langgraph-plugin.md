# LangGraph Plugin Implementation Plan

> **For subagents:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Commit after your task and after any review fixes.

**Goal:** Ship a first `opscanvas-langgraph` tier-1 plugin package that maps public LangGraph execution surfaces into canonical OpsCanvas runs, spans, events, and usage.

**Architecture:** Create a separate Python workspace package under `packages/opscanvas-langgraph` that mirrors the existing `opscanvas-agents` and `opscanvas-claude` package shape. The plugin must depend only on public LangGraph and LangChain Core APIs when wrappers are invoked, use duck-typed recorder tests where possible, and emit the same canonical `Run`/`Span`/`SpanEvent` contracts as every other runtime plugin. LangGraph capture is plugin-specific: use public graph streaming for node/task/checkpoint/message visibility, and a public `GraphCallbackHandler` only for interrupt/resume lifecycle.

**Tech Stack:** Python 3.12, uv workspace, Pydantic contracts from `opscanvas-core`, httpx ingest client pattern from existing plugins, LangGraph public API `>=1.1.10,<2`, LangChain Core callbacks/messages from LangGraph's public dependency set.

---

## Context

Product and engineering docs are local-only and gitignored in the main checkout. Subagents must read or be passed this context:

- Product thesis: OpsCanvas v1 must prove multi-runtime tier-1 ingestion. `opscanvas-langgraph` is the third runtime proof after OpenAI Agents and Claude Agent SDK.
- Engineering rule: native plugins live in `packages/`, are separately versioned pip packages, MIT/open-source friendly, and must emit the same canonical `Run`/`Span`/`SpanEvent` model as every other runtime.
- Runtime plugin contract: every plugin emits canonical runs/spans/events; how it captures is runtime-specific. OpenAI uses a processor lifecycle, Claude uses query wrappers/hooks, and LangGraph should use graph streaming plus callbacks.
- LangGraph local clone: `/Users/rajattiwari/mycelium 2/langgraph`.
- LangGraph public surfaces verified from the local clone:
  - Package: `langgraph` version `1.1.10`, Python `>=3.10`, MIT.
  - Public install: `pip install -U langgraph`.
  - Public graph API: `from langgraph.graph import START, StateGraph`; compiled graphs implement runnable invocation, streaming, batching, and async execution.
  - Public stream modes: `values`, `updates`, `checkpoints`, `tasks`, `debug`, `messages`, `custom`.
  - For observability v0, prefer `stream(..., version="v2", stream_mode=["tasks", "checkpoints", "messages"])` and async equivalent.
  - Public callback API: `langgraph.callbacks.GraphCallbackHandler` with `on_interrupt` and `on_resume`; pass handlers through `config["callbacks"]`.
  - Checkpointers are public but should not be used as the first tracing hook because they change persistence behavior.
- Avoid private/internal LangGraph APIs:
  - No `langgraph._internal.*`.
  - No `langgraph.pregel._*` modules.
  - No private callback managers such as `_GraphCallbackManager`.
  - No dependency on checkpoint internals such as channel versions or pending write ordering.

## Non-Goals

- No custom checkpointer.
- No budget hard-stop enforcement.
- No replay/cassette format.
- No LangSmith dependency.
- No backend API changes.
- No parsing examples/notebook output.
- No reliance on private LangGraph or LangChain internals.

---

### Task 1: Package Scaffold, Runtime Contract Doc, And Shared Exporter Pattern

**Files:**
- Modify: `pyproject.toml`
- Modify: `Makefile`
- Create: `engineering/runtime-plugin-contract.md`
- Create: `packages/opscanvas-langgraph/pyproject.toml`
- Create: `packages/opscanvas-langgraph/README.md`
- Create: `packages/opscanvas-langgraph/src/opscanvas_langgraph/__init__.py`
- Create: `packages/opscanvas-langgraph/src/opscanvas_langgraph/config.py`
- Create: `packages/opscanvas-langgraph/src/opscanvas_langgraph/client.py`
- Create: `packages/opscanvas-langgraph/src/opscanvas_langgraph/exporter.py`
- Create: `packages/opscanvas-langgraph/tests/test_config.py`
- Create: `packages/opscanvas-langgraph/tests/test_client.py`

**Requirements:**
- Add `packages/opscanvas-langgraph` to `tool.uv.workspace.members`.
- Include the package in `make test`, `make lint`, and `make typecheck`.
- Package name is `opscanvas-langgraph`, import package is `opscanvas_langgraph`.
- Package imports must work without `langgraph` installed.
- Optional extra:
  - `langgraph = ["langgraph>=1.1.10,<2"]`
- `OpsCanvasConfig` mirrors existing plugin env behavior:
  - `OPSCANVAS_ENDPOINT`
  - `OPSCANVAS_API_KEY`
  - `OPSCANVAS_PROJECT_ID`
  - `OPSCANVAS_ENVIRONMENT`
  - `OPSCANVAS_TIMEOUT_SECONDS`
- `OpsCanvasClient` posts canonical runs to `/v1/ingest/runs` with optional bearer auth.
- `OpsCanvasExporter` records spans/runs in memory and can optionally send completed runs.
- `engineering/runtime-plugin-contract.md` is the committed one-page plugin authoring doc:
  - Canonical output contract is fixed: `Run`, `Span`, `SpanEvent`, `Usage`.
  - Capture architecture is plugin-specific.
  - Public APIs only; no private SDK internals.
  - Keep optional runtime dependencies optional at package import time.
  - Redact or summarize high-risk raw inputs/outputs by default.
  - Prefer wrappers/callbacks over invasive persistence hooks for v0 integrations.

**Tests:**
- Config env loading and defaults.
- Client posts JSON to `/v1/ingest/runs` and includes bearer header only when configured.
- Client raises clear errors for missing endpoint and non-2xx ingest.
- Exporter records spans and completed runs, respects shutdown, and sends runs only when `send_runs=True`.

**Verification:**
- `uv run pytest packages/opscanvas-langgraph/tests/test_config.py packages/opscanvas-langgraph/tests/test_client.py -q`
- `uv run ruff check packages/opscanvas-langgraph`
- `uv run mypy packages/opscanvas-langgraph/src`

**Commit:** `Add LangGraph plugin package scaffold`

---

### Task 2: LangGraph Recorder And Safe Stream Mapping

**Files:**
- Create: `packages/opscanvas-langgraph/src/opscanvas_langgraph/recorder.py`
- Create: `packages/opscanvas-langgraph/tests/test_recorder.py`
- Modify: `packages/opscanvas-langgraph/src/opscanvas_langgraph/__init__.py`

**Requirements:**
- Implement `LangGraphRunRecorder` that can be used without importing LangGraph.
- Constructor accepts optional `exporter`, `config`, `run_id`, `workflow_name`, `thread_id`, `started_at`, and `stream_modes`.
- On initialization, create a root `agent` span for the graph run.
- Runtime is `langgraph`.
- Project/environment come from config.
- Map public v2 stream chunks by shape, not private classes:
  - Accept either `(mode, payload)` tuples or namespace-qualified `(namespace, mode, payload)` tuples.
  - `tasks` task-start payloads open child spans under the root.
  - `tasks` task-result payloads close the matching child span and attach result/output/error/interrupt metadata.
  - `checkpoints` payloads append `langgraph.checkpoint` events to the root span.
  - `messages` payloads append `langgraph.message` events and, when usage metadata is visible on message objects, aggregate canonical `Usage`.
  - `custom`, `updates`, `values`, and `debug` payloads append safe root events; do not crash.
- Task spans:
  - `kind=SpanKind.custom` for node/task spans in v0.
  - span name from payload `name`, else `langgraph task`.
  - span ID uses a stable safe prefix derived from task `id` when present, else generated deterministic local sequence.
  - input/output are safe summaries, not raw unbounded state dumps.
  - task errors mark span and run failed.
  - task interrupts mark run interrupted unless already failed.
- `record_interrupt(event)` and `record_resume(event)` map public `GraphInterruptEvent`/`GraphResumeEvent`-looking objects to events and metadata.
- `finish(ended_at: datetime | None = None) -> Run` returns and exports one canonical `Run`.
- `fail(exc)` and `interrupt(reason)` helpers mark final status and safe metadata.
- No private LangGraph imports.

**Tests:**
- Pure fake tuples/dicts/dataclasses; do not require LangGraph installed.
- Validate root span/run metadata.
- Validate tasks open/close spans, including error and interrupt status.
- Validate checkpoint/message/custom events.
- Validate message usage aggregation from fake message `usage_metadata`.
- Validate unknown stream shapes become safe events and do not crash.
- Validate `finish()` is idempotent.

**Verification:**
- `uv run pytest packages/opscanvas-langgraph/tests/test_recorder.py -q`
- `uv run ruff check packages/opscanvas-langgraph`
- `uv run mypy packages/opscanvas-langgraph/src`

**Commit:** `Map LangGraph stream events to canonical runs`

---

### Task 3: Callback Handler And Config Merge Helpers

**Files:**
- Create: `packages/opscanvas-langgraph/src/opscanvas_langgraph/callbacks.py`
- Create: `packages/opscanvas-langgraph/tests/test_callbacks.py`
- Modify: `packages/opscanvas-langgraph/src/opscanvas_langgraph/__init__.py`
- Modify: `packages/opscanvas-langgraph/README.md`

**Requirements:**
- Implement `OpsCanvasGraphCallbackHandler`, subclassing public `langgraph.callbacks.GraphCallbackHandler` only when the class is importable.
- Package import must still work when `langgraph` is not installed.
- If the handler is constructed without LangGraph installed, raise a clear RuntimeError with install instructions.
- Handler methods:
  - `on_interrupt(event)` calls recorder `record_interrupt(event)`.
  - `on_resume(event)` calls recorder `record_resume(event)`.
- Implement `merge_opscanvas_callbacks(config: Mapping[str, object] | None, recorder: LangGraphRunRecorder) -> dict[str, object]`.
  - Return a shallow copied config.
  - Preserve existing config values.
  - Preserve existing callback order and append OpsCanvas handler last.
  - Support no callbacks, a single callback, tuples, and lists.
  - Do not mutate the caller's config.
- Implement `get_langgraph_install_error()` or equivalent shared message used by wrappers and handler paths.

**Tests:**
- Monkeypatch/fake `langgraph.callbacks.GraphCallbackHandler` so tests do not need the real package.
- Verify import of `opscanvas_langgraph` works without LangGraph.
- Verify missing LangGraph raises only when constructing the handler or calling wrappers without test seam.
- Verify config merge preserves values and callback order.
- Verify interrupt/resume events record canonical events and statuses.

**Verification:**
- `uv run pytest packages/opscanvas-langgraph/tests/test_callbacks.py -q`
- `uv run ruff check packages/opscanvas-langgraph`
- `uv run mypy packages/opscanvas-langgraph/src`

**Commit:** `Add LangGraph callback recorder`

---

### Task 4: Traced Invoke Wrappers

**Files:**
- Create: `packages/opscanvas-langgraph/src/opscanvas_langgraph/invoke.py`
- Create: `packages/opscanvas-langgraph/tests/test_invoke.py`
- Modify: `packages/opscanvas-langgraph/src/opscanvas_langgraph/__init__.py`
- Modify: `packages/opscanvas-langgraph/README.md`

**Requirements:**
- Implement sync and async wrappers:
  - `traced_invoke(graph, input, *, config=None, exporter=None, opscanvas_config=None, run_id=None, workflow_name=None, stream_modes=None) -> object`
  - `async traced_ainvoke(graph, input, *, config=None, exporter=None, opscanvas_config=None, run_id=None, workflow_name=None, stream_modes=None) -> object`
- Wrappers must:
  - Create a `LangGraphRunRecorder`.
  - Merge OpsCanvas callback handler into the provided LangGraph config.
  - Prefer public `graph.stream(..., version="v2", stream_mode=[...])` / `graph.astream(...)`.
  - Record every yielded stream chunk.
  - Return the final graph output without changing user-visible result semantics.
  - Finish exactly one run on success, exception, cancellation, or generator close.
  - On exceptions, record a failed run then re-raise.
- Default stream modes for invoke wrappers:
  - `["tasks", "checkpoints", "messages", "values"]`
  - Use `values` to recover final output; if no values are seen, fall back to the last non-task payload or `None`.
- Support graphs where `stream`/`astream` returns:
  - plain payloads,
  - `(mode, payload)`,
  - `(namespace, mode, payload)`.
- Avoid calling private graph attributes. Workflow name can come from explicit parameter, `getattr(graph, "name", None)`, or fallback `"LangGraph"`.

**Tests:**
- Fake sync and async graph classes; no real LangGraph/network.
- Verify wrappers pass input/config/version/stream_mode into graph stream calls.
- Verify wrappers yield the same final output as expected from `values` chunks.
- Verify callbacks are merged without mutating caller config.
- Verify success exports one run.
- Verify stream exception exports failed run and re-raises.
- Verify async cancellation/interruption marks run interrupted where appropriate.

**Verification:**
- `uv run pytest packages/opscanvas-langgraph/tests/test_invoke.py -q`
- `uv run ruff check packages/opscanvas-langgraph`
- `uv run mypy packages/opscanvas-langgraph/src`

**Commit:** `Add traced LangGraph invoke wrappers`

---

### Task 5: Traced Stream Wrappers, Docs, And Integration Verification

**Files:**
- Create: `packages/opscanvas-langgraph/src/opscanvas_langgraph/stream.py`
- Create: `packages/opscanvas-langgraph/tests/test_stream.py`
- Modify: `packages/opscanvas-langgraph/src/opscanvas_langgraph/__init__.py`
- Modify: `packages/opscanvas-langgraph/README.md`
- Modify: `README.md`

**Requirements:**
- Implement sync and async streaming wrappers:
  - `traced_stream(graph, input, *, config=None, exporter=None, opscanvas_config=None, run_id=None, workflow_name=None, stream_modes=None, **kwargs)`
  - `traced_astream(graph, input, *, config=None, exporter=None, opscanvas_config=None, run_id=None, workflow_name=None, stream_modes=None, **kwargs)`
- Wrappers must:
  - Yield user chunks unchanged while recording side effects.
  - Merge callbacks as in invoke wrappers.
  - Forward public stream kwargs such as `subgraphs`, `interrupt_before`, `interrupt_after`, `debug`, and `durability`.
  - Finish exactly once when the stream is exhausted, closed, cancelled, or raises.
  - Preserve exceptions after recording failed/interrupted runs.
- README must show:
  - install command with optional extra.
  - `traced_invoke` and `traced_ainvoke` usage.
  - `traced_stream` and `traced_astream` usage for users who already stream.
  - manual `LangGraphRunRecorder` + `merge_opscanvas_callbacks` usage.
  - boundaries: public APIs only, no custom checkpointer, no replay, no budget hard-stops.
- Root README layout mentions `packages/opscanvas-langgraph`.
- Add a lightweight import smoke in tests or verification to ensure package imports without LangGraph installed.

**Tests:**
- Sync stream yields chunks unchanged and exports completed run.
- Async stream yields chunks unchanged and exports completed run.
- Closing or cancelling stream exports interrupted run.
- Underlying stream exception exports failed run and re-raises.
- README examples refer to exported public symbols that exist.

**Verification:**
- `uv run pytest packages/opscanvas-langgraph/tests -q`
- `make verify`
- `pnpm --filter web build`
- `uv run python - <<'PY'\nimport opscanvas_langgraph\nprint(opscanvas_langgraph.__all__)\nPY`

**Commit:** `Add traced LangGraph stream wrappers`

---
