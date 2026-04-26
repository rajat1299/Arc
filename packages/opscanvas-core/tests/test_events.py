from datetime import UTC, datetime

import pytest
from opscanvas_core.events import Run, RunStatus, Span, SpanEvent, SpanKind, Usage
from opscanvas_core.schema_versions import CURRENT_SCHEMA_VERSION
from pydantic import ValidationError


def test_enum_values_are_canonical_contract_values() -> None:
    assert [status.value for status in RunStatus] == [
        "succeeded",
        "failed",
        "interrupted",
        "suboptimal",
        "running",
    ]
    assert [kind.value for kind in SpanKind] == [
        "agent",
        "model_call",
        "tool_call",
        "handoff",
        "guardrail",
        "mcp_list",
        "sandbox_op",
        "retry",
        "custom",
    ]


def test_run_span_event_creation_and_alias_serialization() -> None:
    timestamp = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    event = SpanEvent(
        id="evt_123",
        span_id="span_123",
        name="tool.completed",
        timestamp=timestamp,
        attributes={"ok": True, "attempt": 1},
    )
    span = Span(
        id="span_123",
        run_id="run_123",
        kind=SpanKind.tool_call,
        name="search",
        parent_id=None,
        started_at=timestamp,
        ended_at=timestamp,
        usage=Usage(input_tokens=7, output_tokens=11, total_tokens=18, cost_usd=0.02),
        input={"query": "contract"},
        output={"count": 2},
        attributes={"runtime": "unit-test"},
        events=[event],
    )
    run = Run(
        id="run_123",
        schema_version=CURRENT_SCHEMA_VERSION,
        status=RunStatus.succeeded,
        started_at=timestamp,
        ended_at=timestamp,
        runtime="pytest",
        project_id="project_123",
        environment="test",
        tenant_id="tenant_123",
        user_id="user_123",
        workflow_name="contract-test",
        usage=Usage(total_tokens=18),
        metadata={"trace": "abc"},
        spans=[span],
    )

    dumped = run.model_dump(mode="json", by_alias=True)

    assert dumped["spans"][0]["input"] == {"query": "contract"}
    assert dumped["spans"][0]["output"] == {"count": 2}
    assert "input_data" not in dumped["spans"][0]
    assert "output_data" not in dumped["spans"][0]
    assert dumped["spans"][0]["events"][0]["attributes"] == {"ok": True, "attempt": 1}


def test_extra_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        SpanEvent(
            id="evt_123",
            span_id="span_123",
            name="unexpected",
            timestamp=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
            attributes={},
            extra_field=True,
        )
