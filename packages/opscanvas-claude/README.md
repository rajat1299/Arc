# opscanvas-claude

Claude Agent SDK integration package for OpsCanvas.

This initial scaffold provides the shared configuration, ingest client, and
in-memory exporter used by the Claude plugin. Runtime wrappers are added in
later tasks and keep `claude-agent-sdk` optional at package import time.

Install the optional Claude SDK dependency when using Claude runtime helpers:

```sh
pip install 'opscanvas-claude[claude-agent-sdk]'
```
