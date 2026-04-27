"""Claude Agent SDK hook helpers for OpsCanvas."""

from __future__ import annotations

import importlib
from collections.abc import Awaitable, Callable, Mapping, MutableMapping, Sequence
from datetime import UTC, datetime

from opscanvas_core import Span, SpanKind
from pydantic import JsonValue

from opscanvas_claude.recorder import (
    PROVIDER,
    RUNTIME,
    ClaudeRunRecorder,
    _json_value,
)

HookCallback = Callable[[object, str | None, object], Awaitable[dict[str, object]]]

_HOOK_EVENTS = (
    "UserPromptSubmit",
    "PreToolUse",
    "PostToolUse",
    "PostToolUseFailure",
    "PermissionRequest",
    "SubagentStart",
    "SubagentStop",
    "Notification",
    "PreCompact",
    "Stop",
)

_EVENT_NAMES = {
    "UserPromptSubmit": "claude.user_prompt_submit",
    "PreToolUse": "claude.pre_tool_use",
    "PostToolUse": "claude.post_tool_use",
    "PostToolUseFailure": "claude.post_tool_use_failure",
    "PermissionRequest": "claude.permission_request",
    "SubagentStart": "claude.subagent_start",
    "SubagentStop": "claude.subagent_stop",
    "Notification": "claude.notification",
    "PreCompact": "claude.pre_compact",
    "Stop": "claude.stop",
}


class ClaudeHookRecorder:
    """Attach Claude hook-derived spans and events to a run recorder."""

    def __init__(self, recorder: ClaudeRunRecorder) -> None:
        self.recorder = recorder
        self._tool_spans: dict[str, Span] = {}
        self._subagent_spans: dict[str, Span] = {}

    async def record_hook(
        self,
        hook_input: object,
        tool_use_id: str | None,
        context: object,
    ) -> dict[str, object]:
        """Observe a Claude SDK hook and return no behavior changes."""
        del context
        event_name = _string(_get(hook_input, "hook_event_name")) or "Unknown"
        if event_name == "UserPromptSubmit":
            self._record_root_event(event_name, hook_input)
        elif event_name == "PreToolUse":
            self._record_pre_tool_use(hook_input, tool_use_id)
        elif event_name == "PostToolUse":
            self._record_post_tool_use(hook_input, tool_use_id)
        elif event_name == "PostToolUseFailure":
            self._record_post_tool_use_failure(hook_input, tool_use_id)
        elif event_name == "PermissionRequest":
            self._record_permission_request(hook_input)
        elif event_name == "SubagentStart":
            self._record_subagent_start(hook_input)
        elif event_name == "SubagentStop":
            self._record_subagent_stop(hook_input)
        elif event_name in {"Notification", "PreCompact", "Stop"}:
            self._record_root_event(event_name, hook_input)
        else:
            self.recorder._add_event(
                self.recorder._root_span,
                "claude.hook",
                {"hook_event_name": _json_value(event_name)},
            )
        return {}

    def callback_for(self, event_name: str) -> HookCallback:
        async def callback(
            hook_input: object,
            tool_use_id: str | None,
            context: object,
        ) -> dict[str, object]:
            return await self.record_hook(
                _with_event_name(hook_input, event_name),
                tool_use_id,
                context,
            )

        return callback

    def _record_pre_tool_use(self, hook_input: object, tool_use_id: str | None) -> None:
        resolved_tool_use_id = _string(tool_use_id) or _string(_get(hook_input, "tool_use_id"))
        if not resolved_tool_use_id:
            self._record_root_event("PreToolUse", hook_input, "missing_tool_use_id")
            return

        parent_span = self._parent_span_for(hook_input)
        span = Span(
            id=f"{self.recorder.run_id}_tool_{len(self.recorder._spans)}",
            run_id=self.recorder.run_id,
            kind=SpanKind.tool_call,
            name=_string(_get(hook_input, "tool_name")) or "claude tool",
            parent_id=parent_span.id,
            started_at=datetime.now(UTC),
            input=_json_value(_get(hook_input, "tool_input")),
            attributes={
                "runtime": RUNTIME,
                "provider": PROVIDER,
                "claude.tool_use_id": resolved_tool_use_id,
            },
        )
        _set_attr(span.attributes, "claude.tool_name", _get(hook_input, "tool_name"))
        _set_attr(span.attributes, "claude.session_id", _get(hook_input, "session_id"))
        _set_attr(span.attributes, "claude.agent_id", _get(hook_input, "agent_id"))
        self.recorder._spans.append(span)
        self._tool_spans[resolved_tool_use_id] = span
        self.recorder._add_event(span, _EVENT_NAMES["PreToolUse"], _hook_attributes(hook_input))

    def _record_post_tool_use(self, hook_input: object, tool_use_id: str | None) -> None:
        resolved_tool_use_id = _string(tool_use_id) or _string(_get(hook_input, "tool_use_id"))
        span = self._pop_tool_span(resolved_tool_use_id)
        if span is None:
            self._record_root_event("PostToolUse", hook_input, "unknown_tool_use_id")
            return

        span.output_data = _json_value(_get(hook_input, "tool_response"))
        span.ended_at = datetime.now(UTC)
        self.recorder._add_event(span, _EVENT_NAMES["PostToolUse"], _hook_attributes(hook_input))

    def _record_post_tool_use_failure(
        self,
        hook_input: object,
        tool_use_id: str | None,
    ) -> None:
        resolved_tool_use_id = _string(tool_use_id) or _string(_get(hook_input, "tool_use_id"))
        span = self._pop_tool_span(resolved_tool_use_id)
        if span is None:
            self._record_root_event("PostToolUseFailure", hook_input, "unknown_tool_use_id")
            self.recorder._mark_failed()
            return

        error = _get(hook_input, "error")
        span.output_data = {"error": _json_value(error)}
        span.ended_at = datetime.now(UTC)
        span.attributes["status"] = "failed"
        _set_attr(span.attributes, "claude.error", error)
        self.recorder._add_event(
            span,
            _EVENT_NAMES["PostToolUseFailure"],
            _hook_attributes(hook_input),
        )
        self.recorder._mark_failed()

    def _record_permission_request(self, hook_input: object) -> None:
        tool_use_id = _string(_get(hook_input, "tool_use_id"))
        span = self._tool_spans.get(tool_use_id) if tool_use_id else None
        self.recorder._add_event(
            span or self.recorder._root_span,
            _EVENT_NAMES["PermissionRequest"],
            _hook_attributes(hook_input),
        )

    def _record_subagent_start(self, hook_input: object) -> None:
        agent_id = _string(_get(hook_input, "agent_id"))
        if not agent_id:
            self._record_root_event("SubagentStart", hook_input, "missing_agent_id")
            return

        span = Span(
            id=f"{self.recorder.run_id}_agent_{len(self.recorder._spans)}",
            run_id=self.recorder.run_id,
            kind=SpanKind.agent,
            name=_string(_get(hook_input, "agent_type")) or "claude subagent",
            parent_id=self.recorder._root_span.id,
            started_at=datetime.now(UTC),
            attributes={
                "runtime": RUNTIME,
                "provider": PROVIDER,
                "claude.agent_id": agent_id,
            },
        )
        _set_attr(span.attributes, "claude.agent_type", _get(hook_input, "agent_type"))
        _set_attr(span.attributes, "claude.session_id", _get(hook_input, "session_id"))
        self.recorder._spans.append(span)
        self._subagent_spans[agent_id] = span
        self.recorder._add_event(
            span,
            _EVENT_NAMES["SubagentStart"],
            _hook_attributes(hook_input),
        )

    def _record_subagent_stop(self, hook_input: object) -> None:
        agent_id = _string(_get(hook_input, "agent_id"))
        span = self._subagent_spans.pop(agent_id or "", None)
        if span is None:
            self._record_root_event("SubagentStop", hook_input, "unknown_agent_id")
            return

        span.ended_at = datetime.now(UTC)
        self.recorder._add_event(
            span,
            _EVENT_NAMES["SubagentStop"],
            _hook_attributes(hook_input),
        )

    def _record_root_event(
        self,
        event_name: str,
        hook_input: object,
        warning: str | None = None,
    ) -> None:
        attributes = _hook_attributes(hook_input)
        if warning is not None:
            attributes["opscanvas.warning"] = warning
        self.recorder._add_event(
            self.recorder._root_span,
            _EVENT_NAMES.get(event_name, "claude.hook"),
            attributes,
        )

    def _parent_span_for(self, hook_input: object) -> Span:
        agent_id = _string(_get(hook_input, "agent_id"))
        if agent_id is not None:
            return self._subagent_spans.get(agent_id, self.recorder._root_span)
        return self.recorder._root_span

    def _pop_tool_span(self, tool_use_id: str | None) -> Span | None:
        if tool_use_id is None:
            return None
        return self._tool_spans.pop(tool_use_id, None)


def build_opscanvas_hooks(
    recorder: ClaudeRunRecorder,
    existing_hooks: object | None = None,
) -> object:
    """Build Claude Agent SDK hooks with OpsCanvas observers appended."""
    try:
        claude_agent_sdk = importlib.import_module("claude_agent_sdk")
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Claude Agent SDK hooks require the optional dependency. "
            "Install it with: pip install 'opscanvas-claude[claude-agent-sdk]'"
        ) from exc

    hook_matcher = claude_agent_sdk.HookMatcher
    hook_recorder = ClaudeHookRecorder(recorder)
    merged: dict[str, list[object]] = _copy_existing_hooks(existing_hooks)
    for event_name in _HOOK_EVENTS:
        merged.setdefault(event_name, []).append(
            hook_matcher(matcher=None, hooks=[hook_recorder.callback_for(event_name)])
        )
    return merged


def _copy_existing_hooks(existing_hooks: object | None) -> dict[str, list[object]]:
    if existing_hooks is None:
        return {}
    if not isinstance(existing_hooks, Mapping):
        raise TypeError("existing_hooks must be a mapping of Claude hook events to matchers")

    copied: dict[str, list[object]] = {}
    for event_name, matchers in existing_hooks.items():
        if isinstance(matchers, Sequence) and not isinstance(matchers, str | bytes):
            copied[str(event_name)] = list(matchers)
        else:
            copied[str(event_name)] = [matchers]
    return copied


def _with_event_name(hook_input: object, event_name: str) -> object:
    if _get(hook_input, "hook_event_name") is not None:
        return hook_input
    if isinstance(hook_input, MutableMapping):
        enriched = dict(hook_input)
        enriched["hook_event_name"] = event_name
        return enriched
    return hook_input


def _hook_attributes(hook_input: object) -> dict[str, JsonValue]:
    event_name = _string(_get(hook_input, "hook_event_name"))
    attributes: dict[str, JsonValue] = {}
    for name in _allowed_fields(event_name):
        value = _get(hook_input, name)
        if value is not None:
            attributes[name] = _json_value(_summarize_prompt(value) if name == "prompt" else value)
    return attributes


def _allowed_fields(event_name: str | None) -> tuple[str, ...]:
    common = ("hook_event_name", "session_id", "permission_mode", "agent_id", "agent_type")
    specific = {
        "UserPromptSubmit": ("prompt",),
        "PreToolUse": ("tool_use_id", "tool_name", "tool_input"),
        "PostToolUse": ("tool_use_id", "tool_name", "tool_input", "tool_response"),
        "PostToolUseFailure": ("tool_use_id", "tool_name", "tool_input", "error", "is_interrupt"),
        "PermissionRequest": ("tool_name", "tool_input", "permission_suggestions"),
        "SubagentStart": (),
        "SubagentStop": ("stop_hook_active", "agent_transcript_path"),
        "Notification": ("message", "title", "notification_type"),
        "PreCompact": ("trigger", "custom_instructions"),
        "Stop": ("stop_hook_active",),
    }
    return common + specific.get(event_name or "", ())


def _summarize_prompt(value: object, *, limit: int = 500) -> object:
    if not isinstance(value, str) or len(value) <= limit:
        return value
    return f"{value[: limit - 3]}..."


def _get(source: object, name: str, default: object = None) -> object:
    if isinstance(source, Mapping):
        return source.get(name, default)
    return getattr(source, name, default)


def _string(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _set_attr(target: dict[str, JsonValue], name: str, value: object) -> None:
    if value is not None:
        target[name] = _json_value(value)
