# opscanvas-langgraph

LangGraph integration package for OpsCanvas.

This package provides the shared configuration, ingest client, and in-memory
exporter used by LangGraph tracing adapters. It intentionally does not import
LangGraph at package import time.

Install LangGraph support when using runtime wrappers:

```bash
pip install 'opscanvas-langgraph[langgraph]'
```

Configuration is loaded from the standard OpsCanvas environment variables:

- `OPSCANVAS_ENDPOINT`
- `OPSCANVAS_API_KEY`
- `OPSCANVAS_PROJECT_ID`
- `OPSCANVAS_ENVIRONMENT`
- `OPSCANVAS_TIMEOUT_SECONDS`
