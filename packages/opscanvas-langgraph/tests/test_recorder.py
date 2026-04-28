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
    usage_metadata: dict[str, Any]


@dataclass
class FakeResponseMessage:
    content: str
    usage_metadata: dict[str, Any] | None
    response_metadata: dict[str, Any]


@dataclass
class FakeInterruptEvent:
    reason: str
    value: dict[str, Any]
    namespace: tuple[str, ...]


@dataclass
class FakeResumeEvent:
    value: dict[str, Any]
    config: dict[str, Any]


@dataclass
class FakePublicInterruptEvent:
    run_id: str
    status: str
    checkpoint_id: str
    checkpoint_ns: str
    interrupts: list[dict[str, Any]]


@dataclass
class FakePublicResumeEvent:
    run_id: str
    status: str
    checkpoint_id: str
    checkpoint_ns: str
    interrupts: list[dict[str, Any]]


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


def test_v2_dict_stream_parts_map_type_namespace_and_data() -> None:
    recorder = LangGraphRunRecorder(run_id="run_v2", started_at=STARTED_AT)

    recorder.record_stream_chunk(
        {
            "type": "tasks",
            "ns": ("parent", "child"),
            "data": {"id": "task-1", "name": "lookup", "input": {"secret": "input"}},
        }
    )
    recorder.record_stream_chunk(
        {
            "type": "tasks",
            "ns": ("parent", "child"),
            "data": {
                "id": "task-1",
                "name": "lookup",
                "result": {"secret": "output"},
                "interrupts": [],
            },
        }
    )
    recorder.record_stream_chunk(
        {
            "type": "checkpoints",
            "ns": ["parent"],
            "data": {"values": {"private": "state"}, "next": ("node_a",)},
        }
    )
    recorder.record_stream_chunk(
        {
            "type": "messages",
            "ns": ["parent"],
            "data": (FakeMessage("secret message", {"input_tokens": 5}), {}),
        }
    )
    recorder.record_stream_chunk(
        {"type": "custom", "ns": ["parent"], "data": {"payload": "secret custom"}}
    )
    recorder.record_stream_chunk(
        {
            "type": "values",
            "ns": ["parent"],
            "data": {"interrupts": [{"secret": "pause"}], "output": {"secret": "done"}},
        }
    )
    recorder.record_stream_chunk(
        {"type": "unknown", "ns": ["parent"], "data": {"secret": "unknown"}}
    )
    run = recorder.finish(ENDED_AT)

    task_span = run.spans[1]
    assert task_span.attributes["langgraph.namespace"] == ["parent", "child"]
    assert task_span.attributes["langgraph.status"] == "succeeded"
    events = run.spans[0].events
    assert [event.name for event in events] == [
        "langgraph.checkpoint",
        "langgraph.message",
        "langgraph.custom",
        "langgraph.values",
        "langgraph.stream",
    ]
    assert events[0].attributes["langgraph.namespace"] == ["parent"]
    assert events[0].attributes["langgraph.checkpoint.values"] == {
        "type": "dict",
        "key_count": 1,
    }
    assert events[1].attributes["langgraph.stream_mode"] == "messages"
    assert events[2].attributes["payload"] == {"type": "dict", "key_count": 1}
    assert events[3].attributes["payload"] == {"type": "dict", "key_count": 2}
    assert events[4].attributes["langgraph.stream_mode"] == "unknown"
    assert events[4].attributes["payload"] == {"type": "dict", "key_count": 1}
    assert run.usage is not None
    assert run.usage.input_tokens == 5
    exported = exported_json(run)
    assert "secret message" not in exported
    assert "secret custom" not in exported
    assert "secret" not in exported


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


def test_message_usage_reads_common_nested_detail_shapes() -> None:
    recorder = LangGraphRunRecorder(run_id="run_nested_usage", started_at=STARTED_AT)

    recorder.record_stream_chunk(
        (
            "messages",
            (
                FakeMessage(
                    "one",
                    {
                        "input_tokens": 10,
                        "output_tokens": 4,
                        "input_token_details": {"cache_read": 3},
                        "output_token_details": {"reasoning": 2},
                    },
                ),
                {},
            ),
        )
    )
    recorder.record_stream_chunk(
        (
            "messages",
            (
                FakeResponseMessage(
                    "two",
                    None,
                    {
                        "token_usage": {
                            "prompt_tokens": 20,
                            "completion_tokens": 8,
                            "prompt_tokens_details": {"cached_tokens": 6},
                            "completion_tokens_details": {"reasoning_tokens": 5},
                        }
                    },
                ),
                {},
            ),
        )
    )
    run = recorder.finish(ENDED_AT)

    assert run.usage is not None
    assert run.usage.input_tokens == 30
    assert run.usage.output_tokens == 12
    assert run.usage.cached_input_tokens == 9
    assert run.usage.reasoning_tokens == 7


def test_unknown_stream_shapes_become_safe_events_and_do_not_crash() -> None:
    recorder = LangGraphRunRecorder(run_id="run_unknown", started_at=STARTED_AT)

    recorder.record_stream_chunk({"not": "a tuple"})
    recorder.record_stream_chunk({"type": 1, "data": {"secret": "dict"}})
    recorder.record_stream_chunk(("unknown", SecretObject()))
    recorder.record_stream_chunk(("tasks", SecretObject()))
    run = recorder.finish(ENDED_AT)

    events = run.spans[0].events
    assert [event.name for event in events] == [
        "langgraph.stream",
        "langgraph.stream",
        "langgraph.stream",
        "langgraph.tasks",
    ]
    assert events[0].attributes == {
        "shape": "dict",
        "payload": {"type": "dict", "key_count": 1},
    }
    assert events[1].attributes == {
        "shape": "dict",
        "payload": {"type": "dict", "key_count": 2},
    }
    assert events[2].attributes["payload"] == {"type": "SecretObject"}
    assert events[3].attributes["payload"] == {"type": "SecretObject"}
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


def test_public_interrupt_and_resume_event_fields_are_recorded_safely() -> None:
    recorder = LangGraphRunRecorder(run_id="run_public_lifecycle", started_at=STARTED_AT)

    recorder.record_interrupt(
        FakePublicInterruptEvent(
            run_id="langgraph-run-1",
            status="interrupted",
            checkpoint_id="checkpoint-1",
            checkpoint_ns="node:abc",
            interrupts=[{"value": "secret interrupt"}],
        )
    )
    recorder.record_resume(
        FakePublicResumeEvent(
            run_id="langgraph-run-1",
            status="running",
            checkpoint_id="checkpoint-2",
            checkpoint_ns="node:def",
            interrupts=[],
        )
    )
    run = recorder.finish(ENDED_AT)

    interrupt_event, resume_event = run.spans[0].events
    assert interrupt_event.attributes["run_id"] == "langgraph-run-1"
    assert interrupt_event.attributes["status"] == "interrupted"
    assert interrupt_event.attributes["checkpoint_id"] == "checkpoint-1"
    assert interrupt_event.attributes["checkpoint_ns"] == "node:abc"
    assert interrupt_event.attributes["interrupts"] == {
        "type": "list",
        "item_count": 1,
        "item_types": ["dict"],
    }
    assert resume_event.attributes["run_id"] == "langgraph-run-1"
    assert resume_event.attributes["status"] == "running"
    assert resume_event.attributes["checkpoint_id"] == "checkpoint-2"
    assert resume_event.attributes["checkpoint_ns"] == "node:def"
    assert resume_event.attributes["interrupts"] == {
        "type": "list",
        "item_count": 0,
    }
    assert "secret interrupt" not in exported_json(run)


def test_finish_is_idempotent_and_exports_once() -> None:
    exporter = OpsCanvasExporter()
    recorder = LangGraphRunRecorder(exporter=exporter, run_id="run_once", started_at=STARTED_AT)

    first = recorder.finish(ENDED_AT)
    second = recorder.finish(ENDED_AT + timedelta(seconds=5))

    assert first is second
    assert first.ended_at == ENDED_AT
    assert exporter.runs == [first]
    assert exporter.spans == first.spans
