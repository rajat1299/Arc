from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from opscanvas_claude import ClaudeRunRecorder, OpsCanvasConfig, OpsCanvasExporter
from opscanvas_core import RunStatus, SpanKind

STARTED_AT = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
ENDED_AT = STARTED_AT + timedelta(seconds=2)


@dataclass
class TextBlock:
    text: str


@dataclass
class ToolUseBlock:
    id: str
    name: str
    input: dict[str, Any]


@dataclass
class ToolResultBlock:
    tool_use_id: str
    content: str
    is_error: bool = False


@dataclass
class AssistantMessage:
    message_id: str
    model: str
    content: list[object]
    usage: dict[str, int]
    stop_reason: str | None = None
    session_id: str | None = None
    uuid: str | None = None
    error: object | None = None


@dataclass
class UserMessage:
    content: object


@dataclass
class ResultMessage:
    total_cost_usd: float | None = None
    usage: dict[str, int] | None = None
    is_error: bool = False
    errors: list[str] | None = None
    stop_reason: str | None = None
    session_id: str | None = None
    num_turns: int | None = None
    duration_ms: int | None = None
    duration_api_ms: int | None = None


@dataclass
class SystemMessage:
    subtype: str
    data: dict[str, Any]


@dataclass
class TaskNotificationMessage:
    task_id: str
    status: str
    message: str


@dataclass
class StreamEvent:
    event: str
    data: dict[str, Any]


@dataclass
class StrangeCustomMessage:
    payload: object


def test_assistant_messages_become_model_spans_with_provider_model_and_usage() -> None:
    exporter = OpsCanvasExporter(
        config=OpsCanvasConfig(project_id="project_123", environment="test")
    )
    recorder = ClaudeRunRecorder(
        exporter=exporter,
        run_id="run_123",
        workflow_name="refund assistant",
        started_at=STARTED_AT,
    )

    recorder.record_message(
        AssistantMessage(
            message_id="msg_123",
            model="claude-sonnet-4-5",
            content=[TextBlock("I can help."), ToolUseBlock("tool_1", "search", {"q": "refund"})],
            usage={"input_tokens": 10, "output_tokens": 6, "cache_read_input_tokens": 3},
            stop_reason="tool_use",
            session_id="session_123",
            uuid="uuid_123",
        )
    )
    run = recorder.finish(ENDED_AT)

    assert run.id == "run_123"
    assert run.workflow_name == "refund assistant"
    assert run.runtime == "claude-agent-sdk"
    assert run.project_id == "project_123"
    assert run.environment == "test"
    assert run.status is RunStatus.succeeded
    assert len(run.spans) == 2

    root_span = run.spans[0]
    model_span = run.spans[1]
    assert root_span.kind is SpanKind.agent
    assert root_span.started_at == STARTED_AT
    assert model_span.kind is SpanKind.model_call
    assert model_span.parent_id == root_span.id
    assert model_span.name == "claude-sonnet-4-5"
    assert model_span.input_data == [
        {"text": "I can help."},
        {"id": "tool_1", "name": "search", "input": {"q": "refund"}},
    ]
    assert model_span.output_data == model_span.input_data
    assert model_span.usage is not None
    assert model_span.usage.input_tokens == 10
    assert model_span.usage.output_tokens == 6
    assert model_span.usage.cached_input_tokens == 3
    assert model_span.attributes["runtime"] == "claude-agent-sdk"
    assert model_span.attributes["provider"] == "anthropic"
    assert model_span.attributes["model"] == "claude-sonnet-4-5"
    assert model_span.attributes["claude.message_id"] == "msg_123"
    assert model_span.attributes["claude.stop_reason"] == "tool_use"
    assert model_span.attributes["claude.session_id"] == "session_123"
    assert model_span.attributes["claude.uuid"] == "uuid_123"
    assert [event.name for event in model_span.events] == ["claude.tool_use"]
    assert model_span.events[0].attributes["name"] == "search"

    assert exporter.runs == [run]


def test_user_tool_result_system_stream_and_unknown_messages_record_safe_events() -> None:
    recorder = ClaudeRunRecorder(run_id="run_123", started_at=STARTED_AT)

    recorder.record_message(UserMessage(content={"role": "user", "text": "hello"}))
    recorder.record_message(
        AssistantMessage(
            message_id="msg_123",
            model="claude-sonnet-4-5",
            content=[ToolResultBlock("tool_1", "done")],
            usage={},
        )
    )
    recorder.record_message(SystemMessage(subtype="init", data={"cwd": "/tmp"}))
    recorder.record_message(StreamEvent(event="content_block_delta", data={"delta": "hi"}))
    recorder.record_message(StrangeCustomMessage(payload=object()))

    run = recorder.finish(ENDED_AT)

    root_event_names = [event.name for event in run.spans[0].events]
    assert root_event_names == [
        "claude.user_message",
        "claude.system_message",
        "claude.stream_event",
        "claude.message",
    ]
    assert run.spans[0].events[0].attributes["content"] == {"role": "user", "text": "hello"}
    assert run.spans[0].events[-1].attributes["message_type"] == "StrangeCustomMessage"

    model_span = run.spans[1]
    assert [event.name for event in model_span.events] == ["claude.tool_result"]
    assert model_span.events[0].attributes["tool_use_id"] == "tool_1"


def test_result_message_sets_run_usage_cost_status_and_session_metadata() -> None:
    recorder = ClaudeRunRecorder(run_id="run_123", started_at=STARTED_AT)

    recorder.record_message(
        ResultMessage(
            total_cost_usd=0.25,
            usage={"input_tokens": 11, "output_tokens": 7, "total_tokens": 18},
            is_error=False,
            stop_reason="end_turn",
            session_id="session_123",
            num_turns=3,
            duration_ms=1500,
            duration_api_ms=900,
        )
    )
    run = recorder.finish(ENDED_AT)

    assert run.status is RunStatus.succeeded
    assert run.usage is not None
    assert run.usage.input_tokens == 11
    assert run.usage.output_tokens == 7
    assert run.usage.total_tokens == 18
    assert run.usage.cost_usd == 0.25
    assert run.metadata["claude.session_id"] == "session_123"
    assert run.metadata["claude.stop_reason"] == "end_turn"
    assert run.metadata["claude.num_turns"] == 3
    assert run.metadata["claude.duration_ms"] == 1500
    assert run.metadata["claude.duration_api_ms"] == 900
    assert run.spans[0].events[-1].name == "claude.result"


def test_failed_and_interrupted_results_map_statuses() -> None:
    failed = ClaudeRunRecorder(run_id="run_failed", started_at=STARTED_AT)
    failed.record_message(ResultMessage(is_error=True, errors=["tool failed"]))

    interrupted = ClaudeRunRecorder(run_id="run_interrupted", started_at=STARTED_AT)
    interrupted.record_message(ResultMessage(stop_reason="user_interrupt"))

    stopped_task = ClaudeRunRecorder(run_id="run_stopped", started_at=STARTED_AT)
    stopped_task.record_message(TaskNotificationMessage("task_1", "stopped", "user stopped task"))

    assert failed.finish(ENDED_AT).status is RunStatus.failed
    assert interrupted.finish(ENDED_AT).status is RunStatus.interrupted
    assert stopped_task.finish(ENDED_AT).status is RunStatus.interrupted


def test_assistant_error_and_failed_task_notification_mark_run_failed() -> None:
    assistant_error = ClaudeRunRecorder(run_id="run_assistant_error", started_at=STARTED_AT)
    assistant_error.record_message(
        AssistantMessage(
            message_id="msg_123",
            model="claude-sonnet-4-5",
            content=[],
            usage={},
            error={"message": "model failed"},
        )
    )

    task_failed = ClaudeRunRecorder(run_id="run_task_failed", started_at=STARTED_AT)
    task_failed.record_message(TaskNotificationMessage("task_1", "failed", "tool failed"))

    assert assistant_error.finish(ENDED_AT).status is RunStatus.failed
    assert task_failed.finish(ENDED_AT).status is RunStatus.failed
