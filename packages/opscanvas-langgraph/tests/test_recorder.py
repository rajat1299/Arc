from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from opscanvas_core import RunStatus, SpanKind
from opscanvas_langgraph import LangGraphRunRecorder, OpsCanvasConfig, OpsCanvasExporter

STARTED_AT = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
ENDED_AT = STARTED_AT + timedelta(seconds=2)


def exported_json(value: object) -> str:
    if hasattr(value, "model_dump"):
        return json.dumps(value.model_dump(mode="json"), sort_keys=True)
    return json.dumps(value, sort_keys=True)


@dataclass
class FakeMessage:
    content: str
    usage_metadata: dict[str, int]


@dataclass
class FakeInterruptEvent:
    reason: str
    value: dict[str, Any]
    namespace: tuple[str, ...]


@dataclass
class FakeResumeEvent:
    value: dict[str, Any]
    config: dict[str, Any]


class SecretObject:
    def __repr__(self) -> str:
        return "<SecretObject token=secret>"


def test_root_span_and_run_metadata_come_from_constructor_and_config() -> None:
    exporter = OpsCanvasExporter(
        config=OpsCanvasConfig(project_id="project_123", environment="test")
    )
    recorder = LangGraphRunRecorder(
        exporter=exporter,
        run_id="run_123",
        workflow_name="refund graph",
        thread_id="thread_123",
        started_at=STARTED_AT,
        stream_modes=("tasks", "messages"),
    )

    run = recorder.finish(ENDED_AT)

    assert run.id == "run_123"
    assert run.runtime == "langgraph"
    assert run.workflow_name == "refund graph"
    assert run.project_id == "project_123"
    assert run.environment == "test"
    assert run.status is RunStatus.succeeded
    assert run.metadata == {
        "runtime": "langgraph",
        "langgraph.thread_id": "thread_123",
    }
    assert len(run.spans) == 1
    root = run.spans[0]
    assert root.id == "run_123_root"
    assert root.kind is SpanKind.agent
    assert root.name == "refund graph"
    assert root.started_at == STARTED_AT
    assert root.ended_at == ENDED_AT
    assert root.attributes["runtime"] == "langgraph"
    assert root.attributes["langgraph.thread_id"] == "thread_123"
    assert root.attributes["langgraph.stream_modes"] == ["tasks", "messages"]
    assert exporter.runs == [run]


def test_task_start_and_result_open_and_close_custom_span_with_safe_payloads() -> None:
    recorder = LangGraphRunRecorder(run_id="run_tasks", started_at=STARTED_AT)

    recorder.record_stream_chunk(
        (
            "tasks",
            {
                "id": "task-1",
                "name": "lookup",
                "input": {"secret": "private input"},
                "triggers": ["start"],
            },
        )
    )
    recorder.record_stream_chunk(
        ("tasks", {"id": "task-1", "name": "lookup", "result": {"answer": "secret output"}})
    )
    run = recorder.finish(ENDED_AT)

    assert run.status is RunStatus.succeeded
    assert len(run.spans) == 2
    task_span = run.spans[1]
    assert task_span.kind is SpanKind.custom
    assert task_span.parent_id == run.spans[0].id
    assert task_span.name == "lookup"
    assert task_span.id.startswith("run_tasks_task_")
    assert task_span.attributes["runtime"] == "langgraph"
    assert task_span.attributes["langgraph.task_id"] == "task-1"
    assert task_span.attributes["langgraph.triggers"] == ["start"]
    assert task_span.attributes["langgraph.status"] == "succeeded"
    assert task_span.input_data == {"type": "dict", "key_count": 1}
    assert task_span.output_data == {"type": "dict", "key_count": 1}
    exported = exported_json(run)
    assert "private input" not in exported
    assert "secret output" not in exported


def test_task_without_id_uses_deterministic_local_sequence() -> None:
    recorder = LangGraphRunRecorder(run_id="run_local_task", started_at=STARTED_AT)

    recorder.record_stream_chunk(("tasks", {"name": "anonymous", "input": {"secret": "input"}}))
    recorder.record_stream_chunk(("tasks", {"name": "anonymous", "result": {"secret": "output"}}))
    run = recorder.finish(ENDED_AT)

    task_span = run.spans[1]
    assert task_span.id == "run_local_task_task_1"
    assert task_span.attributes["langgraph.status"] == "succeeded"
    assert len(run.spans) == 2


def test_task_error_marks_span_and_run_failed() -> None:
    recorder = LangGraphRunRecorder(run_id="run_failed", started_at=STARTED_AT)

    recorder.record_stream_chunk(("tasks", {"id": "task-1", "input": {"q": "x"}}))
    recorder.record_stream_chunk(
        ("tasks", {"id": "task-1", "error": {"message": "provider secret"}})
    )
    run = recorder.finish(ENDED_AT)

    task_span = run.spans[1]
    assert run.status is RunStatus.failed
    assert task_span.attributes["langgraph.status"] == "failed"
    assert task_span.attributes["langgraph.error"] == {"type": "dict", "key_count": 1}
    assert "provider secret" not in exported_json(run)


def test_task_interrupt_marks_run_interrupted_unless_already_failed() -> None:
    interrupted = LangGraphRunRecorder(run_id="run_interrupted", started_at=STARTED_AT)
    interrupted.record_stream_chunk(("tasks", {"id": "task-1", "input": None}))
    interrupted.record_stream_chunk(("tasks", {"id": "task-1", "interrupts": ["pause"]}))

    failed_then_interrupted = LangGraphRunRecorder(
        run_id="run_failed_then_interrupted",
        started_at=STARTED_AT,
    )
    failed_then_interrupted.record_stream_chunk(("tasks", {"id": "task-1", "input": None}))
    failed_then_interrupted.record_stream_chunk(("tasks", {"id": "task-1", "error": "boom"}))
    failed_then_interrupted.record_stream_chunk(
        ("tasks", {"id": "task-2", "interrupts": ["pause"]})
    )

    assert interrupted.finish(ENDED_AT).status is RunStatus.interrupted
    assert failed_then_interrupted.finish(ENDED_AT).status is RunStatus.failed


def test_checkpoint_message_and_custom_events_are_recorded_safely() -> None:
    recorder = LangGraphRunRecorder(run_id="run_events", started_at=STARTED_AT)

    recorder.record_stream_chunk(
        (
            ("parent", "child"),
            "checkpoints",
            {
                "config": {"configurable": {"thread_id": "thread_123"}},
                "metadata": {"source": "loop"},
                "values": {"private": "state"},
                "next": ("node_a",),
                "parent_config": None,
                "tasks": [{"id": "task-1"}],
            },
        )
    )
    recorder.record_stream_chunk(
        (
            "messages",
            (
                FakeMessage(
                    content="secret model text",
                    usage_metadata={"input_tokens": 10, "output_tokens": 4, "total_tokens": 14},
                ),
                {"langgraph_step": 2, "langgraph_node": "node_a"},
            ),
        )
    )
    recorder.record_stream_chunk(("custom", {"payload": "secret custom"}))
    run = recorder.finish(ENDED_AT)

    events = run.spans[0].events
    assert [event.name for event in events] == [
        "langgraph.checkpoint",
        "langgraph.message",
        "langgraph.custom",
    ]
    assert events[0].attributes["langgraph.namespace"] == ["parent", "child"]
    assert events[0].attributes["langgraph.checkpoint.values"] == {
        "type": "dict",
        "key_count": 1,
    }
    assert events[1].attributes["message_type"] == "FakeMessage"
    assert events[1].attributes["message"] == {"type": "FakeMessage", "field_count": 2}
    assert events[1].attributes["metadata"] == {
        "langgraph_step": 2,
        "langgraph_node": "node_a",
    }
    assert events[2].attributes["payload"] == {"type": "dict", "key_count": 1}
    assert run.usage is not None
    assert run.usage.input_tokens == 10
    assert run.usage.output_tokens == 4
    assert run.usage.total_tokens == 14
    exported = exported_json(run)
    assert "secret model text" not in exported
    assert "secret custom" not in exported
    assert "private" not in exported


def test_message_usage_aggregates_across_multiple_messages() -> None:
    recorder = LangGraphRunRecorder(run_id="run_usage", started_at=STARTED_AT)

    recorder.record_stream_chunk(
        ("messages", (FakeMessage("one", {"input_tokens": 3, "output_tokens": 2}), {}))
    )
    recorder.record_stream_chunk(
        ("messages", (FakeMessage("two", {"input_tokens": 4, "total_tokens": 10}), {}))
    )
    run = recorder.finish(ENDED_AT)

    assert run.usage is not None
    assert run.usage.input_tokens == 7
    assert run.usage.output_tokens == 2
    assert run.usage.total_tokens == 10


def test_unknown_stream_shapes_become_safe_events_and_do_not_crash() -> None:
    recorder = LangGraphRunRecorder(run_id="run_unknown", started_at=STARTED_AT)

    recorder.record_stream_chunk({"not": "a tuple"})
    recorder.record_stream_chunk(("unknown", SecretObject()))
    recorder.record_stream_chunk(("tasks", SecretObject()))
    run = recorder.finish(ENDED_AT)

    events = run.spans[0].events
    assert [event.name for event in events] == [
        "langgraph.stream",
        "langgraph.stream",
        "langgraph.tasks",
    ]
    assert events[0].attributes == {
        "shape": "dict",
        "payload": {"type": "dict", "key_count": 1},
    }
    assert events[1].attributes["payload"] == {"type": "SecretObject"}
    assert events[2].attributes["payload"] == {"type": "SecretObject"}
    assert "token=secret" not in exported_json(run)


def test_interrupt_resume_fail_and_interrupt_helpers_record_status_and_metadata() -> None:
    interrupted = LangGraphRunRecorder(run_id="run_interrupt", started_at=STARTED_AT)
    interrupted.record_interrupt(
        FakeInterruptEvent(
            reason="approval needed",
            value={"secret": "payload"},
            namespace=("node",),
        )
    )
    interrupted.record_resume(FakeResumeEvent(value={"secret": "resume"}, config={"x": 1}))
    run = interrupted.finish(ENDED_AT)

    assert run.status is RunStatus.interrupted
    assert [event.name for event in run.spans[0].events] == [
        "langgraph.interrupt",
        "langgraph.resume",
    ]
    assert run.spans[0].events[0].attributes["event_type"] == "FakeInterruptEvent"
    assert run.spans[0].events[0].attributes["value"] == {
        "type": "dict",
        "key_count": 1,
    }
    assert run.metadata["langgraph.interrupt"] == {
        "type": "FakeInterruptEvent",
        "field_count": 3,
    }
    assert "payload" not in exported_json(run)

    failed = LangGraphRunRecorder(run_id="run_failed_helper", started_at=STARTED_AT)
    failed.fail(RuntimeError("secret exception"))
    failed.interrupt("later pause")
    failed_run = failed.finish(ENDED_AT)
    assert failed_run.status is RunStatus.failed
    assert failed_run.metadata["langgraph.error"] == {"type": "RuntimeError", "has_error": True}


def test_finish_is_idempotent_and_exports_once() -> None:
    exporter = OpsCanvasExporter()
    recorder = LangGraphRunRecorder(exporter=exporter, run_id="run_once", started_at=STARTED_AT)

    first = recorder.finish(ENDED_AT)
    second = recorder.finish(ENDED_AT + timedelta(seconds=5))

    assert first is second
    assert first.ended_at == ENDED_AT
    assert exporter.runs == [first]
    assert exporter.spans == first.spans
