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
class FakeSpanWithTraceId:
    span_id: str
    trace_id: str
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


def test_no_trace_id_span_does_not_pollute_later_overlapping_trace() -> None:
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    exporter = OpsCanvasExporter()
    processor = OpsCanvasProcessor(exporter=exporter)
    trace_a = FakeTrace("trace_a", "trace A", timestamp, timestamp)
    trace_b = FakeTrace("trace_b", "trace B", timestamp, timestamp)

    processor.on_trace_start(trace_a)
    processor.on_trace_start(trace_b)
    processor.on_span_end(
        FakeSpanWithoutTraceId(
            "span_ambiguous",
            None,
            timestamp,
            timestamp,
            FakeSpanData("agent", name="ambiguous agent"),
        )
    )
    processor.on_trace_end(trace_b)
    processor.on_trace_end(trace_a)

    assert len(exporter.runs) == 2
    assert exporter.runs[0].id == "trace_b"
    assert exporter.runs[0].spans == []
    assert exporter.runs[1].id == "trace_a"
    assert exporter.runs[1].spans == []
    assert [span.id for span in exporter.spans] == ["span_ambiguous"]


def test_public_trace_id_span_buffers_to_matching_overlapping_trace() -> None:
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    exporter = OpsCanvasExporter()
    processor = OpsCanvasProcessor(exporter=exporter)
    trace_a = FakeTrace("trace_a", "trace A", timestamp, timestamp)
    trace_b = FakeTrace("trace_b", "trace B", timestamp, timestamp)

    processor.on_trace_start(trace_a)
    processor.on_trace_start(trace_b)
    processor.on_span_end(
        FakeSpanWithTraceId(
            "span_a",
            "trace_a",
            None,
            timestamp,
            timestamp,
            FakeSpanData("agent", name="trace A agent"),
        )
    )
    processor.on_trace_end(trace_b)
    processor.on_trace_end(trace_a)

    assert len(exporter.runs) == 2
    assert exporter.runs[0].id == "trace_b"
    assert exporter.runs[0].spans == []
    assert exporter.runs[1].id == "trace_a"
    assert [span.id for span in exporter.runs[1].spans] == ["span_a"]
