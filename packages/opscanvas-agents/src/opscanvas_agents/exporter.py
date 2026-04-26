"""In-memory exporter skeleton for OpsCanvas spans.

HTTP shipping will live here later. For now the exporter records canonical spans
in memory so processor mapping can be tested without network calls.
"""

from __future__ import annotations

from collections.abc import Iterable

from opscanvas_core import Span

from opscanvas_agents.config import OpsCanvasConfig


class OpsCanvasExporter:
    """Collect mapped OpsCanvas spans without performing network I/O."""

    def __init__(self, config: OpsCanvasConfig | None = None) -> None:
        self.config = config or OpsCanvasConfig.from_env()
        self.spans: list[Span] = []
        self._shutdown = False

    def export(self, spans: Iterable[Span]) -> None:
        """Record spans in memory."""
        if self._shutdown:
            return

        self.spans.extend(spans)

    def force_flush(self) -> None:
        """Match tracing exporter flush surfaces without network behavior."""

    def shutdown(self) -> None:
        """Mark the exporter as closed."""
        self._shutdown = True
