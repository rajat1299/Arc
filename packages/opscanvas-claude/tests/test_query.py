from __future__ import annotations

import asyncio
import importlib
import sys
import types
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import pytest
from opscanvas_claude import OpsCanvasExporter, traced_query
from opscanvas_core import RunStatus, SpanKind


@dataclass
class FakeHookMatcher:
    matcher: str | None = None
    hooks: list[Any] | None = None

    def __post_init__(self) -> None:
        if self.hooks is None:
            self.hooks = []


@dataclass(frozen=True)
class FakeClaudeAgentOptions:
    hooks: dict[str, list[Any]] | None = None
    model: str = "claude-sonnet-4-5"


@dataclass
class TextBlock:
    text: str


@dataclass
class AssistantMessage:
    message_id: str
    model: str
    content: list[object]
    usage: dict[str, int]


@dataclass
class ResultMessage:
    total_cost_usd: float | None = None
    usage: dict[str, int] | None = None
    is_error: bool = False


def install_fake_claude_sdk(
    monkeypatch: pytest.MonkeyPatch,
    query: object,
) -> None:
    module = types.ModuleType("claude_agent_sdk")
    module.HookMatcher = FakeHookMatcher
    module.ClaudeAgentOptions = FakeClaudeAgentOptions
    module.query = query
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", module)


async def collect_messages(source: AsyncIterator[object]) -> list[object]:
    messages: list[object] = []
    async for message in source:
        messages.append(message)
    return messages


def test_traced_query_yields_messages_unchanged_and_exports_one_run() -> None:
    exporter = OpsCanvasExporter()
    messages = [
        AssistantMessage(
            message_id="msg_123",
            model="claude-sonnet-4-5",
            content=[TextBlock("hello")],
            usage={"input_tokens": 8, "output_tokens": 3},
        ),
        ResultMessage(
            total_cost_usd=0.12,
            usage={"input_tokens": 8, "output_tokens": 3, "total_tokens": 11},
        ),
    ]
    calls: list[dict[str, object]] = []

    async def fake_query(**kwargs: object) -> AsyncIterator[object]:
        calls.append(kwargs)
        for message in messages:
            yield message

    yielded = asyncio.run(
        collect_messages(
            traced_query(
                prompt="hello",
                exporter=exporter,
                run_id="run_query",
                workflow_name="query workflow",
                query_func=fake_query,
            )
        )
    )

    assert yielded == messages
    assert calls == [{"prompt": "hello", "options": None}]
    assert len(exporter.runs) == 1
    run = exporter.runs[0]
    assert run.id == "run_query"
    assert run.workflow_name == "query workflow"
    assert run.status is RunStatus.succeeded
    assert run.usage is not None
    assert run.usage.cost_usd == 0.12
    model_span = next(span for span in run.spans if span.kind is SpanKind.model_call)
    assert model_span.name == "claude-sonnet-4-5"
    assert model_span.usage is not None
    assert model_span.usage.input_tokens == 8


def test_traced_query_imports_public_query_only_when_invoked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import opscanvas_claude

    assert opscanvas_claude.traced_query is traced_query

    seen_options: list[object] = []

    async def fake_sdk_query(**kwargs: object) -> AsyncIterator[object]:
        seen_options.append(kwargs["options"])
        yield ResultMessage()

    install_fake_claude_sdk(monkeypatch, fake_sdk_query)
    exporter = OpsCanvasExporter()

    yielded = asyncio.run(
        collect_messages(traced_query(prompt="hello", exporter=exporter, run_id="run_import"))
    )

    assert yielded == [ResultMessage()]
    assert len(exporter.runs) == 1
    assert isinstance(seen_options[0], FakeClaudeAgentOptions)
    assert seen_options[0].hooks is not None


def test_traced_query_marks_failed_run_and_reraises_on_query_error() -> None:
    exporter = OpsCanvasExporter()

    async def fake_query(**kwargs: object) -> AsyncIterator[object]:
        del kwargs
        yield AssistantMessage(
            message_id="msg_123",
            model="claude-sonnet-4-5",
            content=[],
            usage={"input_tokens": 1},
        )
        raise RuntimeError("claude cli failed")

    with pytest.raises(RuntimeError, match="claude cli failed"):
        asyncio.run(
            collect_messages(
                traced_query(
                    prompt="hello",
                    exporter=exporter,
                    run_id="run_failed",
                    query_func=fake_query,
                )
            )
        )

    assert len(exporter.runs) == 1
    run = exporter.runs[0]
    assert run.status is RunStatus.failed
    assert run.metadata["claude.error.type"] == "RuntimeError"
    assert run.metadata["claude.error.message"] == "claude cli failed"
    assert len([span for span in run.spans if span.kind is SpanKind.model_call]) == 1


def test_traced_query_preserves_dataclass_options_and_customer_hooks_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def customer_hook(
        hook_input: object,
        tool_use_id: str | None,
        context: object,
    ) -> dict[str, object]:
        del hook_input, tool_use_id, context
        return {"customer": True}

    existing_hooks = {"PreToolUse": [FakeHookMatcher(matcher="Bash", hooks=[customer_hook])]}
    options = FakeClaudeAgentOptions(hooks=existing_hooks, model="claude-opus-4-5")
    seen_options: list[FakeClaudeAgentOptions] = []

    async def fake_sdk_query(**kwargs: object) -> AsyncIterator[object]:
        seen_options.append(kwargs["options"])
        yield ResultMessage()

    install_fake_claude_sdk(monkeypatch, fake_sdk_query)

    asyncio.run(
        collect_messages(traced_query(prompt="hello", options=options, run_id="run_options"))
    )

    assert seen_options
    effective_options = seen_options[0]
    assert effective_options is not options
    assert options.hooks is existing_hooks
    assert options.hooks["PreToolUse"] == existing_hooks["PreToolUse"]
    assert effective_options.model == "claude-opus-4-5"
    assert effective_options.hooks is not None
    assert effective_options.hooks["PreToolUse"][0] is existing_hooks["PreToolUse"][0]
    assert effective_options.hooks["PreToolUse"][1].matcher is None


def test_traced_query_works_with_async_callable_returning_async_iterable() -> None:
    async def message_stream() -> AsyncIterator[object]:
        yield ResultMessage()

    async def fake_query(**kwargs: object) -> AsyncIterator[object]:
        del kwargs
        return message_stream()

    exporter = OpsCanvasExporter()

    yielded = asyncio.run(
        collect_messages(
            traced_query(
                prompt="hello",
                exporter=exporter,
                run_id="run_awaitable_query",
                query_func=fake_query,
            )
        )
    )

    assert yielded == [ResultMessage()]
    assert len(exporter.runs) == 1


def test_package_imports_without_claude_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delitem(sys.modules, "claude_agent_sdk", raising=False)
    real_import_module = importlib.import_module

    def fake_import_module(name: str, package: str | None = None) -> types.ModuleType:
        if name == "claude_agent_sdk":
            raise ModuleNotFoundError("No module named 'claude_agent_sdk'")
        return real_import_module(name, package)

    monkeypatch.setattr(importlib, "import_module", fake_import_module)

    import opscanvas_claude

    assert "traced_query" in opscanvas_claude.__all__
