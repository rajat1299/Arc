from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from opscanvas_agents import (
    OpsCanvasConfig,
    OpsCanvasExporter,
    OpsCanvasProcessor,
    build_run_from_trace,
    map_agents_span,
)
from opscanvas_core import RunStatus, SpanKind


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
    started_at: object
    ended_at: object
    span_data: FakeSpanData
    error: object | None = None


@dataclass
class FakeTrace:
    trace_id: str
    name: str
    started_at: object
    ended_at: object
    error: str | None = None


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
    assert exporter.force_flush() is None
    exporter.shutdown()


def test_processor_preserves_iso_timestamp_strings() -> None:
    exporter = OpsCanvasExporter()
    processor = OpsCanvasProcessor(exporter=exporter)

    processor.on_span_end(
        FakeSpan(
            "span_model",
            "trace_123",
            None,
            "2026-01-01T00:00:01.123Z",
            "2026-01-01T00:00:02.456+00:00",
            FakeSpanData("generation", model="gpt-5.1"),
        )
    )

    assert exporter.spans[0].started_at == datetime(2026, 1, 1, 0, 0, 1, 123000, tzinfo=UTC)
    assert exporter.spans[0].ended_at == datetime(2026, 1, 1, 0, 0, 2, 456000, tzinfo=UTC)


def test_exporter_and_processor_flush_methods_follow_sdk_none_contract() -> None:
    exporter = OpsCanvasExporter()
    processor = OpsCanvasProcessor(exporter=exporter)

    assert exporter.export([]) is None
    assert exporter.force_flush() is None
    assert processor.force_flush() is None


def test_build_run_from_trace_maps_public_trace_fields_and_config() -> None:
    config = OpsCanvasConfig(project_id="project_123", environment="test")
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    span = FakeSpan(
        "span_model",
        "trace_123",
        None,
        timestamp,
        timestamp,
        FakeSpanData("generation", model="gpt-5.1"),
    )
    mapped_span = OpsCanvasProcessor(exporter=OpsCanvasExporter(config=config)).exporter
    mapped_span.export([build_span := map_agents_span(span, config)])

    run = build_run_from_trace(
        FakeTrace("trace_123", "refund assistant", timestamp, timestamp),
        mapped_span.spans,
        config,
    )

    assert run.id == "trace_123"
    assert run.runtime == "openai-agents"
    assert run.workflow_name == "refund assistant"
    assert run.project_id == "project_123"
    assert run.environment == "test"
    assert run.status is RunStatus.succeeded
    assert run.spans == [build_span]


def test_exporter_records_completed_runs_without_network_by_default() -> None:
    exporter = OpsCanvasExporter()
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    processor = OpsCanvasProcessor(exporter=exporter)

    processor.on_span_end(
        FakeSpan(
            "span_model",
            "trace_123",
            None,
            timestamp,
            timestamp,
            FakeSpanData("generation", model="gpt-5.1"),
        )
    )
    processor.on_trace_end(FakeTrace("trace_123", "refund assistant", timestamp, timestamp))

    assert len(exporter.runs) == 1
    assert exporter.runs[0].id == "trace_123"
    assert exporter.runs[0].spans == exporter.spans


def test_exporter_sends_completed_runs_when_enabled() -> None:
    class FakeClient:
        def __init__(self) -> None:
            self.runs: list[object] = []

        def ingest_run(self, run: object) -> None:
            self.runs.append(run)

    client = FakeClient()
    exporter = OpsCanvasExporter(client=client, send_runs=True)
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    processor = OpsCanvasProcessor(exporter=exporter)

    processor.on_trace_end(FakeTrace("trace_123", "refund assistant", timestamp, timestamp))

    assert exporter.runs == client.runs


def test_build_run_from_trace_marks_clear_failures_failed() -> None:
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    run = build_run_from_trace(
        FakeTrace("trace_123", "refund assistant", timestamp, timestamp, error="tool failed"),
        [],
        OpsCanvasConfig(),
    )

    assert run.status is RunStatus.failed


def test_build_run_from_trace_marks_span_errors_failed() -> None:
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    mapped_span = map_agents_span(
        FakeSpan(
            "span_tool",
            "trace_123",
            None,
            timestamp,
            timestamp,
            FakeSpanData("function", tool_name="search"),
            error={"message": "tool failed", "data": {"retryable": False}},
        )
    )

    run = build_run_from_trace(
        FakeTrace("trace_123", "refund assistant", timestamp, timestamp),
        [mapped_span],
        OpsCanvasConfig(),
    )

    assert mapped_span.attributes["error"] == {
        "message": "tool failed",
        "data": {"retryable": False},
    }
    assert run.status is RunStatus.failed
