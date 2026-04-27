# Claude Agent SDK Plugin Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ship a first `opscanvas-claude` tier-1 plugin package that maps public Claude Agent SDK messages/hooks into canonical OpsCanvas runs, spans, events, and usage.

**Architecture:** Create a separate Python workspace package under `packages/opscanvas-claude` that mirrors the existing `opscanvas-agents` package shape. The first version depends only on public `claude_agent_sdk` exports when runtime wrappers are invoked, uses duck-typed mapping for tests, and deliberately avoids `_internal` SDK modules and transcript parsing. The plugin records one canonical run per wrapped `query()` call and provides hook callbacks that customers can merge into `ClaudeAgentOptions.hooks`.

**Tech Stack:** Python 3.12, uv workspace, Pydantic contracts from `opscanvas-core`, httpx ingest client pattern from `opscanvas-agents`, Claude Agent SDK public API `>=0.1.68,<0.2`.

---

## Context

Product and engineering docs are local-only and gitignored in the main checkout. Subagents must read or be passed this context:

- Product thesis: OpsCanvas v1 must prove multi-runtime tier-1 ingestion. `opscanvas-claude` is the second runtime proof after OpenAI Agents.
- Engineering rule: native plugins live in `packages/`, are separately versioned pip packages, MIT/open-source friendly, and must emit the same canonical `Run`/`Span`/`SpanEvent` model as every other runtime.
- SDK reuse rule: for Claude Agent SDK, depend on public top-level exports only; build the translator ourselves; avoid `_internal` modules and opaque transcript parsing.
- Claude SDK local clone: `/Users/rajattiwari/mycelium 2/claude-agent-sdk-python`.
- Claude SDK public surfaces verified from the local clone:
  - `query()`, `ClaudeSDKClient`, `ClaudeAgentOptions`, `HookMatcher`, hook/message dataclasses from top-level `claude_agent_sdk`.
  - Message dataclasses: `UserMessage`, `AssistantMessage`, `ResultMessage`, `SystemMessage` subclasses, `StreamEvent`, `RateLimitEvent`.
  - Content blocks: `TextBlock`, `ThinkingBlock`, `ToolUseBlock`, `ToolResultBlock`, `ServerToolUseBlock`, `ServerToolResultBlock`.
  - Hook events: `PreToolUse`, `PostToolUse`, `PostToolUseFailure`, `UserPromptSubmit`, `Stop`, `SubagentStart`, `SubagentStop`, `PermissionRequest`, `Notification`, `PreCompact`.
  - There is no public `SessionStart`/`SessionEnd` hook input in `HookEvent`; synthesize run lifecycle in the wrapper instead.
  - Local SDK version is `0.1.68`, alpha; pin `claude-agent-sdk>=0.1.68,<0.2` as an optional extra.

## Non-Goals

- No SessionStore replay/transcript parsing.
- No budget hard-stop enforcement yet.
- No ClaudeSDKClient interactive wrapper yet.
- No partial token delta reconstruction.
- No dependency on private `claude_agent_sdk._internal.*`.
- No backend API changes.

---

### Task 1: Package Scaffold And Shared Exporter Pattern

**Files:**
- Modify: `pyproject.toml`
- Modify: `Makefile`
- Create: `packages/opscanvas-claude/pyproject.toml`
- Create: `packages/opscanvas-claude/README.md`
- Create: `packages/opscanvas-claude/src/opscanvas_claude/__init__.py`
- Create: `packages/opscanvas-claude/src/opscanvas_claude/config.py`
- Create: `packages/opscanvas-claude/src/opscanvas_claude/client.py`
- Create: `packages/opscanvas-claude/src/opscanvas_claude/exporter.py`
- Create: `packages/opscanvas-claude/tests/test_config.py`
- Create: `packages/opscanvas-claude/tests/test_client.py`

**Requirements:**
- Add `packages/opscanvas-claude` to `tool.uv.workspace.members`.
- Include the package in `make test`, `make lint`, and `make typecheck`.
- Package name is `opscanvas-claude`, import package is `opscanvas_claude`.
- Package imports must work without `claude-agent-sdk` installed.
- Optional extra:
  - `claude-agent-sdk = ["claude-agent-sdk>=0.1.68,<0.2"]`
- `OpsCanvasConfig` mirrors `opscanvas-agents` env behavior:
  - `OPSCANVAS_ENDPOINT`
  - `OPSCANVAS_API_KEY`
  - `OPSCANVAS_PROJECT_ID`
  - `OPSCANVAS_ENVIRONMENT`
  - `OPSCANVAS_TIMEOUT_SECONDS`
- `OpsCanvasClient` posts canonical runs to `/v1/ingest/runs` with optional bearer auth.
- `OpsCanvasExporter` records spans/runs in memory and can optionally send completed runs.

**Tests:**
- Config env loading and defaults.
- Client posts JSON to `/v1/ingest/runs` and includes bearer header only when configured.
- Client raises clear errors for missing endpoint and non-2xx ingest.
- Exporter records spans and completed runs, respects shutdown, and sends runs only when `send_runs=True`.

**Verification:**
- `uv run pytest packages/opscanvas-claude/tests/test_config.py packages/opscanvas-claude/tests/test_client.py -q`
- `uv run ruff check packages/opscanvas-claude`
- `uv run mypy packages/opscanvas-claude/src`

**Commit:** `Add Claude plugin package scaffold`

---

### Task 2: Message-To-Run Mapping

**Files:**
- Create: `packages/opscanvas-claude/src/opscanvas_claude/recorder.py`
- Create: `packages/opscanvas-claude/tests/test_recorder_messages.py`
- Modify: `packages/opscanvas-claude/src/opscanvas_claude/__init__.py`

**Requirements:**
- Implement a `ClaudeRunRecorder` that can be used without importing the Claude SDK.
- Constructor accepts optional `exporter`, `config`, `run_id`, `workflow_name`, and `started_at`.
- On initialization, create a root `agent` span for the run.
- `record_message(message: object) -> None` maps public-looking message objects by class name and attributes:
  - `UserMessage`: append a `claude.user_message` event to the root span. Store safe content summary/JSON in event attributes.
  - `AssistantMessage`: create a `model_call` span under the root span.
    - span name is model when present, otherwise `claude assistant message`.
    - input/output captures the content blocks as JSON-safe values.
    - usage maps to canonical `Usage`.
    - attributes include `runtime`, `provider="anthropic"`, `model`, `claude.message_id`, `claude.stop_reason`, `claude.session_id`, `claude.uuid`, and `claude.error` when present.
    - tool/server tool blocks inside assistant content create `claude.tool_use` events on the model span.
  - `ResultMessage`: update run summary fields; record `claude.result` event; map `total_cost_usd`, usage, `is_error`, `errors`, `stop_reason`, `session_id`, `num_turns`, `duration_ms`, `duration_api_ms`.
  - `SystemMessage`, `TaskStartedMessage`, `TaskProgressMessage`, `TaskNotificationMessage`: append system/task events to root span; task starts/notifications may create/close custom spans only if IDs are clear.
  - `StreamEvent` and `RateLimitEvent`: append events to root span.
- `finish(ended_at: datetime | None = None) -> Run` returns and exports one canonical `Run`.
- Status:
  - default `succeeded`
  - `failed` when result `is_error` is true, assistant has error, task notification status is `failed`, or errors exist
  - `interrupted` when stop reason/status clearly indicates interrupt/stopped
- Runtime is `claude-agent-sdk`.
- Project/environment come from config.
- No private SDK imports.

**Tests:**
- Pure fake dataclasses or imported public Claude SDK dataclasses may be used, but tests must not call the real CLI/network.
- Validate:
  - assistant messages become model spans with provider/model/usage.
  - tool use/result blocks produce events or fallback data without crashing.
  - result message sets run usage/cost/status/session metadata.
  - failed/interrupted results map statuses correctly.
  - unknown/custom messages become safe events and do not crash.

**Verification:**
- `uv run pytest packages/opscanvas-claude/tests/test_recorder_messages.py -q`
- `uv run ruff check packages/opscanvas-claude`
- `uv run mypy packages/opscanvas-claude/src`

**Commit:** `Map Claude SDK messages to canonical runs`

---

### Task 3: Hook Recorder And Claude Options Helpers

**Files:**
- Create: `packages/opscanvas-claude/src/opscanvas_claude/hooks.py`
- Create: `packages/opscanvas-claude/tests/test_hooks.py`
- Modify: `packages/opscanvas-claude/src/opscanvas_claude/__init__.py`
- Modify: `packages/opscanvas-claude/README.md`

**Requirements:**
- Implement a hook recorder class or helper that attaches hook-derived spans/events to a `ClaudeRunRecorder`.
- Public API should avoid requiring Claude SDK import at package import time.
- Provide `build_opscanvas_hooks(recorder: ClaudeRunRecorder, existing_hooks: object | None = None) -> object`.
  - When `claude_agent_sdk` is installed, return a hook dict compatible with `ClaudeAgentOptions.hooks`.
  - If not installed and the function is called, raise a clear RuntimeError with install instructions.
  - Preserve/merge existing hooks by appending OpsCanvas hooks after customer hooks for the same events.
- Hook mapping:
  - `UserPromptSubmit`: root event with prompt summary.
  - `PreToolUse`: open `tool_call` span keyed by `tool_use_id`.
  - `PostToolUse`: close matching tool span; record response output.
  - `PostToolUseFailure`: close matching tool span as failed; set error attributes.
  - `PermissionRequest`: root/tool event.
  - `SubagentStart`: open nested `agent` span keyed by `agent_id`.
  - `SubagentStop`: close matching subagent span.
  - `Notification`, `PreCompact`, `Stop`: root events.
- Hook callbacks must return `{}` so they observe without changing Claude behavior.
- Missing IDs, duplicate closes, and out-of-order hooks must not crash; record safe events instead.

**Tests:**
- Use monkeypatch/fake `claude_agent_sdk` module for `HookMatcher` so tests do not require actual CLI.
- Verify hook merge order.
- Verify Pre/Post tool hook opens/closes `tool_call` span with input/output and attributes.
- Verify failure hook marks run/spans failed after `finish()`.
- Verify subagent start/stop opens/closes nested agent span.
- Verify no SDK installed path raises only when helper is called, not on package import.

**Verification:**
- `uv run pytest packages/opscanvas-claude/tests/test_hooks.py -q`
- `uv run ruff check packages/opscanvas-claude`
- `uv run mypy packages/opscanvas-claude/src`

**Commit:** `Add Claude SDK hook recorder`

---

### Task 4: Query Wrapper, Docs, And Integration Verification

**Files:**
- Create: `packages/opscanvas-claude/src/opscanvas_claude/query.py`
- Create: `packages/opscanvas-claude/tests/test_query.py`
- Modify: `packages/opscanvas-claude/src/opscanvas_claude/__init__.py`
- Modify: `packages/opscanvas-claude/README.md`
- Modify: `README.md`

**Requirements:**
- Implement `async def traced_query(*, prompt, options=None, exporter=None, config=None, run_id=None, workflow_name=None, query_func=None)`.
- `traced_query` behavior:
  - Imports/calls public `claude_agent_sdk.query` only when invoked.
  - Creates a `ClaudeRunRecorder`.
  - Merges OpsCanvas hooks into provided `ClaudeAgentOptions` when possible.
  - Yields the same messages produced by the underlying query.
  - Records every yielded message.
  - Calls `finish()` exactly once in success and failure paths.
  - On underlying exception, finish a failed run with error metadata, then re-raise.
- `query_func` test seam accepts an async callable returning/yielding message objects so tests avoid real Claude CLI/network.
- Docs show:
  - install command with optional extra.
  - basic `traced_query` usage.
  - advanced manual `ClaudeRunRecorder` + `build_opscanvas_hooks` usage.
  - boundaries: no transcript replay, no hard-stop budgets, no private SDK APIs.
- Root README layout mentions `packages/opscanvas-claude`.

**Tests:**
- `traced_query` yields messages unchanged and exports one run.
- It records assistant/result messages into canonical spans.
- It preserves importability without Claude SDK installed.
- It marks failed run and re-raises when underlying query errors.
- It does not mutate provided options in surprising ways; when hooks are present, customer hooks still run first.

**Verification:**
- `uv run pytest packages/opscanvas-claude/tests -q`
- `make verify`
- `pnpm --filter web build`
- `uv run python - <<'PY'\nimport opscanvas_claude\nprint(opscanvas_claude.__all__)\nPY`

**Commit:** `Add traced Claude query wrapper`

---

### Task 5: Final Review And Merge

**Files:**
- All branch changes.

**Requirements:**
- Run full final review by a separate subagent over `origin/main..HEAD`.
- Reviewer must check:
  - no private Claude SDK imports;
  - package import works without optional SDK;
  - canonical payloads validate against `opscanvas-core`;
  - no secret/header logging;
  - Makefile/workspace include new package;
  - docs do not overclaim replay/budget support.
- Fix blockers in separate commits.

**Verification:**
- `git status --short --branch`
- `uv sync --all-packages`
- `make verify`
- `pnpm --filter web build`
- `uv run pytest packages/opscanvas-claude/tests -q`

**Commit:** only if review fixes are needed.

