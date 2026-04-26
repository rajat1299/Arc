from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from opscanvas_agents import OpsCanvasConfig, OpsCanvasExporter, OpsCanvasProcessor
from opscanvas_core import SpanKind


@dataclass
class FakeSpanData:
    type: str
    name: str | None = None
    input: Any = None
    output: Any = None
    model: str | None = None
    tool_name: str | None = None


@dataclass
class FakeSpan:
    span_id: str
    trace_id: str
    parent_id: str | None
    started_at: datetime
    ended_at: datetime | None
    span_data: FakeSpanData


def test_processor_maps_known_openai_agents_span_types() -> None:
    exporter = OpsCanvasExporter()
    processor = OpsCanvasProcessor(exporter=exporter)
    started_at = datetime(2026, 1, 1, tzinfo=UTC)

    spans = [
        FakeSpan("span_agent", "trace_123", None, started_at, started_at, FakeSpanData("agent")),
        FakeSpan(
            "span_model",
            "trace_123",
            "span_agent",
            started_at,
            started_at,
            FakeSpanData("generation", model="gpt-5.1", input={"prompt": "hi"}),
        ),
        FakeSpan(
            "span_tool",
            "trace_123",
            "span_agent",
            started_at,
            started_at,
            FakeSpanData("function", tool_name="search", output={"ok": True}),
        ),
    ]

    for span in spans:
        processor.on_span_end(span)

    assert [span.kind for span in exporter.spans] == [
        SpanKind.agent,
        SpanKind.model_call,
        SpanKind.tool_call,
    ]
    assert exporter.spans[1].name == "gpt-5.1"
    assert exporter.spans[1].input_data == {"prompt": "hi"}
    assert exporter.spans[2].name == "search"
    assert exporter.spans[2].output_data == {"ok": True}


def test_exporter_uses_config_metadata_and_stays_in_memory() -> None:
    exporter = OpsCanvasExporter(
        config=OpsCanvasConfig(project_id="project_123", environment="test")
    )
    processor = OpsCanvasProcessor(exporter=exporter)
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)

    processor.on_span_end(
        FakeSpan(
            "span_guardrail",
            "trace_123",
            None,
            timestamp,
            timestamp,
            FakeSpanData("guardrail", name="policy check"),
        )
    )

    assert len(exporter.spans) == 1
    assert exporter.spans[0].kind is SpanKind.guardrail
    assert exporter.spans[0].attributes["project_id"] == "project_123"
    assert exporter.spans[0].attributes["environment"] == "test"
    assert exporter.force_flush() is True
    exporter.shutdown()
