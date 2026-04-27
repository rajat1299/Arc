# opscanvas-claude

Claude Agent SDK integration package for OpsCanvas.

This package provides shared configuration, ingest client/exporter helpers,
Claude Agent SDK recorders, hook helpers, and a `traced_query()` wrapper for
canonical OpsCanvas runs. The package can be imported without
`claude-agent-sdk`; Claude-specific runtime helpers import the SDK only when
called.

Install the optional Claude SDK dependency when using Claude runtime helpers:

```sh
pip install 'opscanvas-claude[claude-agent-sdk]'
```

Basic query tracing:

```python
from opscanvas_claude import traced_query

async for message in traced_query(
    prompt="Summarize this repository",
    workflow_name="repository summary",
):
    print(message)
```

`traced_query()` yields the same Claude Agent SDK messages produced by
`claude_agent_sdk.query`, records each message into one canonical run, and
appends OpsCanvas hook observers to `ClaudeAgentOptions` when it can do so
without mutating the provided options object.

Advanced manual hook recording:

```python
from claude_agent_sdk import ClaudeAgentOptions, query
from opscanvas_claude import ClaudeRunRecorder, build_opscanvas_hooks

recorder = ClaudeRunRecorder(workflow_name="research assistant")
options = ClaudeAgentOptions(
    hooks=build_opscanvas_hooks(recorder),
)

async for message in query(prompt="Summarize this repository", options=options):
    recorder.record_message(message)

run = recorder.finish()
```

`build_opscanvas_hooks(recorder, existing_hooks=...)` preserves existing Claude
hooks and appends OpsCanvas observers after customer hooks for each event. Hook
callbacks return `{}` so they do not alter Claude behavior.

Current boundaries: no transcript replay, no hard-stop budget enforcement, and
no private Claude SDK APIs.
