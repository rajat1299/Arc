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

Install the optional OpenAI Agents SDK dependency when using the plugin in an
application:

```bash
pip install "opscanvas-agents[openai-agents]"
```

The current exporter is an in-memory collector. Future HTTP shipping will be
implemented behind the exporter surface without changing the processor API.
