from __future__ import annotations

import asyncio
import importlib
import sys
import types
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from opscanvas_claude import ClaudeRunRecorder, build_opscanvas_hooks
from opscanvas_core import RunStatus, SpanKind

STARTED_AT = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
ENDED_AT = STARTED_AT + timedelta(seconds=2)


@dataclass
class FakeHookMatcher:
    matcher: str | None = None
    hooks: list[Any] | None = None
    timeout: float | None = None

    def __post_init__(self) -> None:
        if self.hooks is None:
            self.hooks = []


def install_fake_claude_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    module = types.ModuleType("claude_agent_sdk")
    module.HookMatcher = FakeHookMatcher
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", module)


def run_hook(hooks: object, event_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    hook_dict = hooks
    assert isinstance(hook_dict, dict)
    matcher = hook_dict[event_name][-1]
    callback = matcher.hooks[0]
    return asyncio.run(callback(payload, payload.get("tool_use_id"), {"signal": None}))


def run_hook_with_tool_use_id(
    hooks: object,
    event_name: str,
    payload: dict[str, Any],
    tool_use_id: str | None,
) -> dict[str, Any]:
    hook_dict = hooks
    assert isinstance(hook_dict, dict)
    matcher = hook_dict[event_name][-1]
    callback = matcher.hooks[0]
    return asyncio.run(callback(payload, tool_use_id, {"signal": None}))


def test_build_opscanvas_hooks_merges_after_customer_hooks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_fake_claude_sdk(monkeypatch)
    recorder = ClaudeRunRecorder(run_id="run_hooks", started_at=STARTED_AT)
    customer_calls: list[str] = []

    async def customer_hook(
        hook_input: object,
        tool_use_id: str | None,
        context: object,
    ) -> dict[str, Any]:
        customer_calls.append(f"{hook_input}:{tool_use_id}:{context}")
        return {"customer": True}

    existing_hooks = {
        "PreToolUse": [FakeHookMatcher(matcher="Bash", hooks=[customer_hook])],
        "Notification": [FakeHookMatcher(matcher=None, hooks=[customer_hook])],
    }

    hooks = build_opscanvas_hooks(recorder, existing_hooks)

    assert hooks is not existing_hooks
    assert len(hooks["PreToolUse"]) == 2
    assert hooks["PreToolUse"][0] is existing_hooks["PreToolUse"][0]
    assert hooks["PreToolUse"][1].matcher is None
    assert len(hooks["Notification"]) == 2
    assert len(hooks["PostToolUse"]) == 1

    output = run_hook(
        hooks,
        "PreToolUse",
        {
            "hook_event_name": "PreToolUse",
            "tool_use_id": "tool_123",
            "tool_name": "Bash",
            "tool_input": {"command": "pwd"},
        },
    )

    assert output == {}
    assert customer_calls == []


def test_tool_hooks_open_and_close_tool_call_span(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_fake_claude_sdk(monkeypatch)
    recorder = ClaudeRunRecorder(run_id="run_tool", started_at=STARTED_AT)
    hooks = build_opscanvas_hooks(recorder)

    assert run_hook(
        hooks,
        "PreToolUse",
        {
            "hook_event_name": "PreToolUse",
            "tool_use_id": "tool_123",
            "tool_name": "Bash",
            "tool_input": {"command": "pwd"},
            "session_id": "session_123",
        },
    ) == {}
    assert run_hook(
        hooks,
        "PostToolUse",
        {
            "hook_event_name": "PostToolUse",
            "tool_use_id": "tool_123",
            "tool_name": "Bash",
            "tool_input": {"command": "pwd"},
            "tool_response": {"stdout": "/tmp"},
        },
    ) == {}

    run = recorder.finish(ENDED_AT)
    tool_span = next(span for span in run.spans if span.kind is SpanKind.tool_call)
    assert tool_span.name == "Bash"
    assert tool_span.parent_id == run.spans[0].id
    assert tool_span.input_data == {"command": "pwd"}
    assert tool_span.output_data == {"stdout": "/tmp"}
    assert tool_span.ended_at is not None
    assert tool_span.attributes["runtime"] == "claude-agent-sdk"
    assert tool_span.attributes["provider"] == "anthropic"
    assert tool_span.attributes["claude.tool_use_id"] == "tool_123"
    assert tool_span.attributes["claude.session_id"] == "session_123"
    assert [event.name for event in tool_span.events] == [
        "claude.pre_tool_use",
        "claude.post_tool_use",
    ]


def test_failure_hook_closes_span_and_marks_run_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_fake_claude_sdk(monkeypatch)
    recorder = ClaudeRunRecorder(run_id="run_failure", started_at=STARTED_AT)
    hooks = build_opscanvas_hooks(recorder)

    run_hook(
        hooks,
        "PreToolUse",
        {
            "hook_event_name": "PreToolUse",
            "tool_use_id": "tool_123",
            "tool_name": "Read",
            "tool_input": {"file_path": "/missing"},
        },
    )
    run_hook(
        hooks,
        "PostToolUseFailure",
        {
            "hook_event_name": "PostToolUseFailure",
            "tool_use_id": "tool_123",
            "tool_name": "Read",
            "tool_input": {"file_path": "/missing"},
            "error": "file does not exist",
        },
    )

    run = recorder.finish(ENDED_AT)
    tool_span = next(span for span in run.spans if span.kind is SpanKind.tool_call)
    assert run.status is RunStatus.failed
    assert tool_span.attributes["claude.error"] == "file does not exist"
    assert tool_span.attributes["status"] == "failed"
    assert tool_span.output_data == {"error": "file does not exist"}


def test_subagent_hooks_open_and_close_nested_agent_span(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_fake_claude_sdk(monkeypatch)
    recorder = ClaudeRunRecorder(run_id="run_subagent", started_at=STARTED_AT)
    hooks = build_opscanvas_hooks(recorder)

    run_hook(
        hooks,
        "SubagentStart",
        {
            "hook_event_name": "SubagentStart",
            "agent_id": "agent_123",
            "agent_type": "code-reviewer",
            "session_id": "session_123",
        },
    )
    run_hook(
        hooks,
        "SubagentStop",
        {
            "hook_event_name": "SubagentStop",
            "agent_id": "agent_123",
            "agent_type": "code-reviewer",
            "stop_hook_active": False,
        },
    )

    run = recorder.finish(ENDED_AT)
    subagent_span = next(
        span for span in run.spans if span.kind is SpanKind.agent and span.id != run.spans[0].id
    )
    assert subagent_span.name == "code-reviewer"
    assert subagent_span.parent_id == run.spans[0].id
    assert subagent_span.ended_at is not None
    assert subagent_span.attributes["claude.agent_id"] == "agent_123"
    assert [event.name for event in subagent_span.events] == [
        "claude.subagent_start",
        "claude.subagent_stop",
    ]


def test_missing_duplicate_and_out_of_order_hook_ids_record_safe_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_fake_claude_sdk(monkeypatch)
    recorder = ClaudeRunRecorder(run_id="run_safe", started_at=STARTED_AT)
    hooks = build_opscanvas_hooks(recorder)

    run_hook(hooks, "PreToolUse", {"hook_event_name": "PreToolUse", "tool_name": "Bash"})
    run_hook(
        hooks,
        "PostToolUse",
        {
            "hook_event_name": "PostToolUse",
            "tool_use_id": "missing",
            "tool_name": "Bash",
            "tool_response": "done",
        },
    )
    run_hook(
        hooks,
        "SubagentStop",
        {"hook_event_name": "SubagentStop", "agent_id": "missing", "agent_type": "general"},
    )
    run_hook(
        hooks,
        "PostToolUse",
        {
            "hook_event_name": "PostToolUse",
            "tool_use_id": "missing",
            "tool_name": "Bash",
            "tool_response": "done again",
        },
    )

    run = recorder.finish(ENDED_AT)
    event_names = [event.name for event in run.spans[0].events]
    assert event_names == [
        "claude.pre_tool_use",
        "claude.post_tool_use",
        "claude.subagent_stop",
        "claude.post_tool_use",
    ]
    assert run.spans[0].events[0].attributes["opscanvas.warning"] == "missing_tool_use_id"
    assert run.spans[0].events[1].attributes["opscanvas.warning"] == "unknown_tool_use_id"
    assert run.spans[0].events[2].attributes["opscanvas.warning"] == "unknown_agent_id"
    assert run.spans[0].events[3].attributes["opscanvas.warning"] == "unknown_tool_use_id"


def test_root_only_hooks_record_events(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_claude_sdk(monkeypatch)
    recorder = ClaudeRunRecorder(run_id="run_root", started_at=STARTED_AT)
    hooks = build_opscanvas_hooks(recorder)

    for event_name, payload in [
        ("UserPromptSubmit", {"hook_event_name": "UserPromptSubmit", "prompt": "hello"}),
        (
            "PermissionRequest",
            {
                "hook_event_name": "PermissionRequest",
                "tool_name": "Bash",
                "tool_input": {"command": "rm -rf /tmp/nope"},
            },
        ),
        ("Notification", {"hook_event_name": "Notification", "message": "working"}),
        ("PreCompact", {"hook_event_name": "PreCompact", "trigger": "manual"}),
        ("Stop", {"hook_event_name": "Stop", "stop_hook_active": False}),
    ]:
        assert run_hook(hooks, event_name, payload) == {}

    run = recorder.finish(ENDED_AT)
    assert [event.name for event in run.spans[0].events] == [
        "claude.user_prompt_submit",
        "claude.permission_request",
        "claude.notification",
        "claude.pre_compact",
        "claude.stop",
    ]
    assert run.spans[0].events[0].attributes["prompt_length"] == 5
    assert "prompt" not in run.spans[0].events[0].attributes


def test_permission_request_uses_callback_tool_use_id_for_active_tool_span(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_fake_claude_sdk(monkeypatch)
    recorder = ClaudeRunRecorder(run_id="run_permission_tool", started_at=STARTED_AT)
    hooks = build_opscanvas_hooks(recorder)

    run_hook(
        hooks,
        "PreToolUse",
        {
            "hook_event_name": "PreToolUse",
            "tool_use_id": "tool_123",
            "tool_name": "Bash",
            "tool_input": {"command": "pwd"},
        },
    )
    run_hook_with_tool_use_id(
        hooks,
        "PermissionRequest",
        {
            "hook_event_name": "PermissionRequest",
            "tool_name": "Bash",
            "tool_input": {"command": "pwd"},
            "permission_suggestions": [{"decision": "allow"}],
        },
        "tool_123",
    )

    run = recorder.finish(ENDED_AT)
    root_span = run.spans[0]
    tool_span = next(span for span in run.spans if span.kind is SpanKind.tool_call)
    assert "claude.permission_request" not in [event.name for event in root_span.events]
    assert [event.name for event in tool_span.events] == [
        "claude.pre_tool_use",
        "claude.permission_request",
    ]
    assert tool_span.events[1].attributes["tool_name"] == "Bash"
    assert tool_span.events[1].attributes["tool_input"] == {"command": "pwd"}


def test_secret_bearing_hook_fields_are_not_recorded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_fake_claude_sdk(monkeypatch)
    recorder = ClaudeRunRecorder(run_id="run_secrets", started_at=STARTED_AT)
    hooks = build_opscanvas_hooks(recorder)

    run_hook(
        hooks,
        "UserPromptSubmit",
        {"hook_event_name": "UserPromptSubmit", "prompt": "secret prompt text"},
    )
    run_hook(
        hooks,
        "Notification",
        {
            "hook_event_name": "Notification",
            "message": "secret notification body",
            "title": "secret notification title",
            "notification_type": "info",
        },
    )
    run_hook(
        hooks,
        "PreCompact",
        {
            "hook_event_name": "PreCompact",
            "trigger": "manual",
            "custom_instructions": "secret compact instructions",
        },
    )
    run_hook(
        hooks,
        "SubagentStop",
        {
            "hook_event_name": "SubagentStop",
            "agent_id": "missing",
            "agent_type": "general",
            "agent_transcript_path": "/tmp/secret-transcript.jsonl",
        },
    )

    run = recorder.finish(ENDED_AT)
    event_attributes = [event.attributes for event in run.spans[0].events]
    assert event_attributes[0]["prompt_length"] == len("secret prompt text")
    assert "prompt" not in event_attributes[0]
    assert event_attributes[1]["notification_type"] == "info"
    assert "message" not in event_attributes[1]
    assert "title" not in event_attributes[1]
    assert event_attributes[2]["trigger"] == "manual"
    assert event_attributes[2]["has_custom_instructions"] is True
    assert "custom_instructions" not in event_attributes[2]
    assert "agent_transcript_path" not in event_attributes[3]
    assert "secret prompt text" not in str(event_attributes)
    assert "secret notification body" not in str(event_attributes)
    assert "secret notification title" not in str(event_attributes)
    assert "secret compact instructions" not in str(event_attributes)
    assert "secret-transcript" not in str(event_attributes)


def test_missing_sdk_raises_only_when_helper_is_called(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import opscanvas_claude

    assert opscanvas_claude.ClaudeRunRecorder is ClaudeRunRecorder

    real_import_module = importlib.import_module

    def fake_import_module(name: str, package: str | None = None) -> types.ModuleType:
        if name == "claude_agent_sdk":
            raise ModuleNotFoundError("No module named 'claude_agent_sdk'")
        return real_import_module(name, package)

    monkeypatch.setattr(importlib, "import_module", fake_import_module)

    with pytest.raises(RuntimeError, match="pip install 'opscanvas-claude\\[claude-agent-sdk\\]'"):
        build_opscanvas_hooks(ClaudeRunRecorder(run_id="run_missing", started_at=STARTED_AT))
