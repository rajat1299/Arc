# OpsCanvas Agents

OpenAI Agents SDK plugin skeleton for OpsCanvas.

This package intentionally imports the `agents` SDK only when
`configure_opscanvas()` is called. Importing `opscanvas_agents` works without the
SDK installed, which keeps tests and downstream packages free of OpenAI network
or SDK requirements.

```python
from opscanvas_agents import configure_opscanvas

configure_opscanvas()
```

By default, the exporter records spans and completed runs in memory only. HTTP
shipping is opt-in:

```python
from opscanvas_agents import OpsCanvasConfig, OpsCanvasExporter, OpsCanvasProcessor

config = OpsCanvasConfig(
    endpoint="https://api.opscanvas.example",
    api_key="opscanvas_key",
    project_id="project_123",
    environment="production",
)
exporter = OpsCanvasExporter(config=config, send_runs=True)
processor = OpsCanvasProcessor(exporter=exporter)
```

Install the optional OpenAI Agents SDK dependency when using the plugin in an
application:

```bash
pip install "opscanvas-agents[openai-agents]"
```

The run builder maps only public-looking trace fields such as IDs, names, and
timestamps. As a skeleton limitation, completed traces default to `succeeded`
unless trace or span attributes clearly indicate failure.
