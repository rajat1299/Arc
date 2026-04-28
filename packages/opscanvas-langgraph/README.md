# opscanvas-langgraph

LangGraph integration package for OpsCanvas.

This package provides the shared configuration, ingest client, and in-memory
exporter used by LangGraph tracing adapters. It intentionally keeps LangGraph
optional at package import time.

Install LangGraph support when using runtime wrappers:

```bash
pip install 'opscanvas-langgraph[langgraph]'
```

## Callback recording

Use `merge_opscanvas_callbacks` when you already own a LangGraph config and want
OpsCanvas to record public interrupt and resume lifecycle callbacks:

```python
from opscanvas_langgraph import LangGraphRunRecorder, merge_opscanvas_callbacks

recorder = LangGraphRunRecorder(workflow_name="Support graph")
config = merge_opscanvas_callbacks(
    {"configurable": {"thread_id": "ticket-123"}},
    recorder,
)

result = graph.invoke({"input": "hello"}, config=config)
run = recorder.finish()
```

The merge helper returns a shallow-copied config, preserves existing values, and
appends the OpsCanvas callback after any existing callbacks. Callback manager
objects are copied when possible and receive the handler through
`add_handler(..., inherit=True)`.

Configuration is loaded from the standard OpsCanvas environment variables:

- `OPSCANVAS_ENDPOINT`
- `OPSCANVAS_API_KEY`
- `OPSCANVAS_PROJECT_ID`
- `OPSCANVAS_ENVIRONMENT`
- `OPSCANVAS_TIMEOUT_SECONDS`
