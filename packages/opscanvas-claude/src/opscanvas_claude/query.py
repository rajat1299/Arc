"""Async Claude Agent SDK query wrapper for OpsCanvas tracing."""

from __future__ import annotations

import copy
import importlib
import inspect
from collections.abc import AsyncIterator, Callable
from dataclasses import is_dataclass, replace
from typing import Any, Protocol, cast

from pydantic import JsonValue

from opscanvas_claude.config import OpsCanvasConfig
from opscanvas_claude.exporter import OpsCanvasExporter
from opscanvas_claude.hooks import build_opscanvas_hooks
from opscanvas_claude.recorder import ClaudeRunRecorder, _json_value

QueryFunc = Callable[..., object]


class _MutableHooksOptions(Protocol):
    hooks: object


async def traced_query(
    *,
    prompt: object,
    options: object | None = None,
    exporter: OpsCanvasExporter | None = None,
    config: OpsCanvasConfig | None = None,
    run_id: str | None = None,
    workflow_name: str | None = None,
    query_func: QueryFunc | None = None,
) -> AsyncIterator[object]:
    """Run Claude Agent SDK ``query`` and record yielded messages as one run."""
    recorder = ClaudeRunRecorder(
        exporter=exporter,
        config=config,
        run_id=run_id,
        workflow_name=workflow_name,
    )
    sdk_module = None
    if query_func is None:
        sdk_module = _import_claude_agent_sdk()
        query_func = sdk_module.query

    effective_options = _options_with_opscanvas_hooks(options, recorder, sdk_module)

    try:
        async for message in _call_query(query_func, prompt=prompt, options=effective_options):
            recorder.record_message(message)
            yield message
    except BaseException as exc:
        _record_exception(recorder, exc)
        recorder.finish()
        raise
    else:
        recorder.finish()


def _import_claude_agent_sdk() -> Any:
    try:
        return importlib.import_module("claude_agent_sdk")
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Claude Agent SDK query tracing requires the optional dependency. "
            "Install it with: pip install 'opscanvas-claude[claude-agent-sdk]'"
        ) from exc


def _options_with_opscanvas_hooks(
    options: object | None,
    recorder: ClaudeRunRecorder,
    sdk_module: Any | None,
) -> object | None:
    if sdk_module is None and options is None:
        return None

    if sdk_module is None:
        try:
            sdk_module = importlib.import_module("claude_agent_sdk")
        except ModuleNotFoundError:
            return options

    existing_hooks = getattr(options, "hooks", None) if options is not None else None
    hooks = build_opscanvas_hooks(recorder, existing_hooks)
    if options is None:
        options_type = getattr(sdk_module, "ClaudeAgentOptions", None)
        if options_type is None:
            return None
        return cast(object, options_type(hooks=hooks))

    if _is_dataclass_instance(options) and _has_dataclass_field(options, "hooks"):
        return cast(object, replace(cast(Any, options), hooks=hooks))

    copied_options = copy.copy(options)
    if hasattr(copied_options, "hooks"):
        cast(_MutableHooksOptions, copied_options).hooks = hooks
        return copied_options
    return options


async def _call_query(
    query_func: QueryFunc,
    *,
    prompt: object,
    options: object | None,
) -> AsyncIterator[object]:
    result = query_func(prompt=prompt, options=options)
    if inspect.isawaitable(result):
        result = await result

    if not hasattr(result, "__aiter__"):
        raise TypeError("Claude query function must return an async iterable")

    async for message in result:
        yield message


def _record_exception(recorder: ClaudeRunRecorder, exc: BaseException) -> None:
    recorder._mark_failed()
    recorder._metadata["claude.error.type"] = type(exc).__name__
    message = str(exc)
    if message:
        recorder._metadata["claude.error.message"] = _safe_error_message(message)


def _safe_error_message(message: str) -> JsonValue:
    return _json_value(message)


def _is_dataclass_instance(value: object) -> bool:
    return is_dataclass(value) and not isinstance(value, type)


def _has_dataclass_field(value: object, name: str) -> bool:
    return name in getattr(value, "__dataclass_fields__", {})
