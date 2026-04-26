"""OpenAI Agents SDK integration for OpsCanvas."""

from __future__ import annotations

from importlib import import_module
from typing import Protocol, cast

from opscanvas_agents.config import OpsCanvasConfig
from opscanvas_agents.exporter import OpsCanvasExporter
from opscanvas_agents.processor import OpsCanvasProcessor

__all__ = [
    "OpsCanvasConfig",
    "OpsCanvasExporter",
    "OpsCanvasProcessor",
    "configure_opscanvas",
]


class _AgentsModule(Protocol):
    def add_trace_processor(self, processor: object) -> None: ...


def configure_opscanvas(
    config: OpsCanvasConfig | None = None,
    exporter: OpsCanvasExporter | None = None,
) -> OpsCanvasProcessor:
    """Register an OpsCanvas tracing processor with OpenAI Agents."""
    try:
        agents = cast(_AgentsModule, import_module("agents"))
    except ImportError as exc:
        raise RuntimeError(
            "OpenAI Agents SDK is required to configure OpsCanvas. "
            "Install it with: pip install 'opscanvas-agents[openai-agents]'"
        ) from exc

    processor = OpsCanvasProcessor(exporter=exporter, config=config)
    agents.add_trace_processor(processor)
    return processor
