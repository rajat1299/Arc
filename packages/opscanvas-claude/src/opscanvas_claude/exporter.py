"""In-memory exporter for OpsCanvas spans and completed runs."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from opscanvas_core import Run, Span

from opscanvas_claude.client import OpsCanvasClient
from opscanvas_claude.config import OpsCanvasConfig


class _RunIngestClient(Protocol):
    def ingest_run(self, run: Run) -> None: ...


class OpsCanvasExporter:
    """Collect mapped spans and optionally send completed canonical runs."""

    def __init__(
        self,
        config: OpsCanvasConfig | None = None,
        *,
        client: _RunIngestClient | None = None,
        send_runs: bool = False,
    ) -> None:
        self.config = config or OpsCanvasConfig.from_env()
        self.spans: list[Span] = []
        self.runs: list[Run] = []
        self._client = client
        self._send_runs = send_runs
        self._shutdown = False

    def export(self, spans: Iterable[Span]) -> None:
        """Record spans in memory."""
        if self._shutdown:
            return

        self.spans.extend(spans)

    def export_run(self, run: Run) -> None:
        """Record a completed canonical run and send it when network export is enabled."""
        if self._shutdown:
            return

        self.runs.append(run)
        if not self._send_runs:
            return

        if self._client is None:
            self._client = OpsCanvasClient(config=self.config)
        self._client.ingest_run(run)

    def force_flush(self) -> None:
        """Match tracing exporter flush surfaces without network behavior."""

    def shutdown(self) -> None:
        """Mark the exporter as closed."""
        self._shutdown = True
