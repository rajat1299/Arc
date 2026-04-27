import json
from datetime import UTC, datetime

from opscanvas_api.storage import (
    run_to_clickhouse_row,
    span_events_to_clickhouse_rows,
    spans_to_clickhouse_rows,
)
from opscanvas_core.events import Run, RunStatus, Span, SpanEvent, SpanKind, Usage
from opscanvas_core.schema_versions import CURRENT_SCHEMA_VERSION


def test_rich_run_maps_to_clickhouse_rows() -> None:
    run = Run(
        id="run_rich",
        schema_version=CURRENT_SCHEMA_VERSION,
        status=RunStatus.succeeded,
        started_at=datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC),
        ended_at=datetime(2026, 1, 1, 12, 0, 3, 250000, tzinfo=UTC),
        runtime="openai-agents-python",
        project_id="123e4567-e89b-12d3-a456-426614174000",
        environment="local-dev",
        tenant_id="tenant_123",
        user_id="user_123",
        workflow_name="support-triage",
        usage=Usage(input_tokens=10, output_tokens=20, total_tokens=30, cost_usd=0.123),
        metadata={"z": 1, "a": {"nested": True}},
        spans=[
            Span(
                id="span_model",
                run_id="run_rich",
                kind=SpanKind.model_call,
                name="call model",
                started_at=datetime(2026, 1, 1, 12, 0, 1, tzinfo=UTC),
                ended_at=datetime(2026, 1, 1, 12, 0, 2, 500000, tzinfo=UTC),
                usage=Usage(input_tokens=10, output_tokens=20, total_tokens=30),
                input={"prompt": "hello", "values": [2, 1]},
                output={"text": "world"},
                attributes={
                    "provider": "openai",
                    "agent.model": "gpt-5.4",
                    "service.tier": "priority",
                    "z": 1,
                    "a": True,
                },
                events=[
                    SpanEvent(
                        id="evt_token",
                        span_id="span_model",
                        name="token.delta",
                        timestamp=datetime(2026, 1, 1, 12, 0, 1, 500000, tzinfo=UTC),
                        attributes={"delta": "hi", "index": 0},
                    )
                ],
            ),
            Span(
                id="span_tool",
                run_id="run_rich",
                kind=SpanKind.tool_call,
                name="fallback_search",
                parent_id="span_model",
                started_at=datetime(2026, 1, 1, 12, 0, 2, tzinfo=UTC),
                ended_at=datetime(2026, 1, 1, 12, 0, 2, 100000, tzinfo=UTC),
                input={"query": "status"},
                output={"count": 1},
                attributes={"tool.name": "search_docs"},
            ),
        ],
    )

    run_row = run_to_clickhouse_row(run)
    span_rows = spans_to_clickhouse_rows(run)
    event_rows = span_events_to_clickhouse_rows(run)

    assert run_row == {
        "org_id": None,
        "project_id": "123e4567-e89b-12d3-a456-426614174000",
        "environment_id": None,
        "environment": "local-dev",
        "run_id": "run_rich",
        "schema_version": CURRENT_SCHEMA_VERSION,
        "runtime": "openai-agents-python",
        "status": "succeeded",
        "started_at": datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC),
        "ended_at": datetime(2026, 1, 1, 12, 0, 3, 250000, tzinfo=UTC),
        "duration_ms": 3250,
        "input_tokens": 10,
        "output_tokens": 20,
        "cached_input_tokens": None,
        "reasoning_tokens": None,
        "audio_input_tokens": None,
        "audio_output_tokens": None,
        "total_tokens": 30,
        "batch_discount_multiplier": None,
        "cost_usd": 0.123,
        "tenant_id": "tenant_123",
        "user_id": "user_123",
        "workflow_name": "support-triage",
        "metadata_json": '{"a":{"nested":true},"z":1}',
        "runtime_attributes_json": "{}",
    }
    assert span_rows[0]["duration_ms"] == 1500
    assert span_rows[0]["input_json"] == '{"prompt":"hello","values":[2,1]}'
    assert span_rows[0]["output_json"] == '{"text":"world"}'
    assert span_rows[0]["attributes_json"] == (
        '{"a":true,"agent.model":"gpt-5.4","provider":"openai",'
        '"service.tier":"priority","z":1}'
    )
    assert span_rows[0]["provider"] == "openai"
    assert span_rows[0]["model"] == "gpt-5.4"
    assert span_rows[0]["tool_name"] is None
    assert span_rows[0]["service_tier"] == "priority"
    assert span_rows[1]["parent_span_id"] == "span_model"
    assert span_rows[1]["tool_name"] == "search_docs"
    assert span_rows[1]["input_tokens"] is None
    assert event_rows == [
        {
            "org_id": None,
            "project_id": "123e4567-e89b-12d3-a456-426614174000",
            "environment_id": None,
            "run_id": "run_rich",
            "span_id": "span_model",
            "event_id": "evt_token",
            "name": "token.delta",
            "timestamp": datetime(2026, 1, 1, 12, 0, 1, 500000, tzinfo=UTC),
            "attributes_json": '{"delta":"hi","index":0}',
        }
    ]
    assert json.loads(span_rows[0]["input_json"]) == {"prompt": "hello", "values": [2, 1]}


def test_running_run_and_open_span_have_null_durations_and_missing_usage() -> None:
    run = Run(
        id="run_running",
        schema_version=CURRENT_SCHEMA_VERSION,
        status=RunStatus.running,
        started_at=datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC),
        runtime="pytest",
        project_id="project_not_uuid",
        environment="environment_not_uuid",
        spans=[
            Span(
                id="span_running_tool",
                run_id="run_running",
                kind=SpanKind.tool_call,
                name="lookup_customer",
                started_at=datetime(2026, 1, 1, 12, 0, 1, tzinfo=UTC),
                attributes={"tool": "crm_lookup", "model": "ignored-for-tool"},
            )
        ],
    )

    run_row = run_to_clickhouse_row(run)
    span_row = spans_to_clickhouse_rows(run)[0]

    assert run_row["ended_at"] is None
    assert run_row["duration_ms"] is None
    assert run_row["project_id"] is None
    assert run_row["environment_id"] is None
    assert run_row["environment"] == "environment_not_uuid"
    assert run_row["input_tokens"] is None
    assert run_row["total_tokens"] is None
    assert span_row["ended_at"] is None
    assert span_row["duration_ms"] is None
    assert span_row["tool_name"] == "crm_lookup"
    assert span_row["cost_usd"] is None
