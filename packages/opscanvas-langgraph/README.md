# opscanvas-langgraph

LangGraph integration package for OpsCanvas.

This package provides the shared configuration, ingest client, and in-memory
exporter used by LangGraph tracing adapters. It intentionally keeps LangGraph
optional at package import time.

Install LangGraph support when using runtime wrappers:

```bash
pip install 'opscanvas-langgraph[langgraph]'
```

## Traced invoke

Use `traced_invoke` or `traced_ainvoke` when you want normal invoke-style final
outputs and an OpsCanvas run recorded from LangGraph's public `stream` APIs:

```python
from opscanvas_langgraph import traced_invoke

result = traced_invoke(
    graph,
    {"input": "hello"},
    config={"configurable": {"thread_id": "ticket-123"}},
    workflow_name="Support graph",
)
```

```python
from opscanvas_langgraph import traced_ainvoke

result = await traced_ainvoke(graph, {"input": "hello"})
```

Invoke wrappers request public LangGraph stream mode `["tasks", "checkpoints",
"messages", "values"]` with `version="v2"`. The final return value comes from
the latest `values` chunk, falling back to the last non-task payload when a graph
does not emit values.

## Traced stream

Use `traced_stream` or `traced_astream` when your application already consumes
LangGraph stream chunks. The wrappers yield each user-visible chunk unchanged
and record OpsCanvas side effects as the stream is consumed:

```python
from opscanvas_langgraph import traced_stream

for chunk in traced_stream(
    graph,
    {"input": "hello"},
    config={"configurable": {"thread_id": "ticket-123"}},
    workflow_name="Support graph",
    subgraphs=True,
):
    handle_chunk(chunk)
```

```python
from opscanvas_langgraph import traced_astream

async for chunk in traced_astream(graph, {"input": "hello"}, durability="sync"):
    await handle_chunk(chunk)
```

If an async stream may be consumed only partially, close it explicitly so the
interrupted run is exported promptly:

```python
from contextlib import aclosing
from opscanvas_langgraph import traced_astream

async with aclosing(traced_astream(graph, {"input": "hello"})) as chunks:
    async for chunk in chunks:
        if should_stop(chunk):
            break
```

Stream wrappers request public LangGraph stream mode `["tasks", "checkpoints",
"messages", "values"]` with `version="v2"` by default. Pass `stream_modes="values"`
or a sequence such as `["messages", "values"]` to choose visible modes. Public
stream kwargs such as `subgraphs`, `interrupt_before`, `interrupt_after`,
`debug`, and `durability` are forwarded to LangGraph.

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

## Boundaries

This package records through public LangGraph and LangChain callback APIs only.
It does not install a custom checkpointer, replay persisted graph state, enforce
budget hard-stops, or depend on private LangGraph internals.
