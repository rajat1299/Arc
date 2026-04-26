from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from opscanvas_agents import OpsCanvasExporter, OpsCanvasProcessor


@dataclass
class FakeSpanData:
    type: str
    name: str | None = None
    input: Any = None
    output: Any = None


@dataclass
class FakeSpanWithoutTraceId:
    span_id: str
    parent_id: str | None
    started_at: object
    ended_at: object
    span_data: FakeSpanData


@dataclass
class FakeTrace:
    trace_id: str
    name: str
    started_at: object
    ended_at: object


def test_trace_lifecycle_exports_one_run_from_buffered_spans() -> None:
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    exporter = OpsCanvasExporter()
    processor = OpsCanvasProcessor(exporter=exporter)

    processor.on_trace_start(FakeTrace("trace_123", "refund assistant", timestamp, timestamp))
    processor.on_span_end(
        FakeSpanWithoutTraceId(
            "span_agent",
            None,
            timestamp,
            timestamp,
            FakeSpanData("agent", name="refund agent"),
        )
    )
    processor.on_span_end(
        FakeSpanWithoutTraceId(
            "span_tool",
            "span_agent",
            timestamp,
            timestamp,
            FakeSpanData("function", name="lookup order", output={"ok": True}),
        )
    )
    processor.on_trace_end(FakeTrace("trace_123", "refund assistant", timestamp, timestamp))

    assert len(exporter.runs) == 1
    run = exporter.runs[0]
    assert run.id == "trace_123"
    assert [span.id for span in run.spans] == ["span_agent", "span_tool"]
    assert {span.run_id for span in run.spans} == {"trace_123"}


def test_span_without_matching_trace_start_keeps_safe_standalone_export() -> None:
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    exporter = OpsCanvasExporter()
    processor = OpsCanvasProcessor(exporter=exporter)

    processor.on_span_end(
        FakeSpanWithoutTraceId(
            "span_orphan",
            None,
            timestamp,
            timestamp,
            FakeSpanData("agent", name="orphan agent"),
        )
    )

    assert len(exporter.spans) == 1
    assert exporter.spans[0].id == "span_orphan"
