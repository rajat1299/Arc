from __future__ import annotations

import asyncio
import importlib
import sys
from collections.abc import AsyncIterator, Iterator
from types import ModuleType

import pytest
from opscanvas_core import RunStatus
from opscanvas_langgraph.exporter import OpsCanvasExporter


class FakeGraphCallbackHandler:
    def __init__(self) -> None:
        self.base_initialized = True


class FakeSyncGraph:
    name = "Fake graph"

    def __init__(self, chunks: list[object]) -> None:
        self.chunks = chunks
        self.calls: list[dict[str, object]] = []

    def stream(
        self,
        input: object,
        *,
        config: dict[str, object],
        version: str,
        stream_mode: list[str],
    ) -> Iterator[object]:
        self.calls.append(
            {
                "input": input,
                "config": config,
                "version": version,
                "stream_mode": stream_mode,
            }
        )
        yield from self.chunks


class FailingSyncGraph:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def stream(
        self,
        input: object,
        *,
        config: dict[str, object],
        version: str,
        stream_mode: list[str],
    ) -> Iterator[object]:
        self.calls.append(
            {
                "input": input,
                "config": config,
                "version": version,
                "stream_mode": stream_mode,
            }
        )
        yield ("values", {"partial": True})
        raise RuntimeError("stream failed")


class ClosingFailingSyncStream:
    def __init__(self) -> None:
        self._yielded = False

    def __iter__(self) -> ClosingFailingSyncStream:
        return self

    def __next__(self) -> object:
        if not self._yielded:
            self._yielded = True
            return ("values", {"partial": True})
        raise RuntimeError("stream failed")

    def close(self) -> None:
        raise RuntimeError("close failed")


class ClosingFailingSyncGraph:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def stream(
        self,
        input: object,
        *,
        config: dict[str, object],
        version: str,
        stream_mode: list[str],
    ) -> ClosingFailingSyncStream:
        self.calls.append(
            {
                "input": input,
                "config": config,
                "version": version,
                "stream_mode": stream_mode,
            }
        )
        return ClosingFailingSyncStream()


class FakeAsyncGraph:
    name = "Async graph"

    def __init__(self, chunks: list[object]) -> None:
        self.chunks = chunks
        self.calls: list[dict[str, object]] = []

    async def astream(
        self,
        input: object,
        *,
        config: dict[str, object],
        version: str,
        stream_mode: list[str],
    ) -> AsyncIterator[object]:
        self.calls.append(
            {
                "input": input,
                "config": config,
                "version": version,
                "stream_mode": stream_mode,
            }
        )
        for chunk in self.chunks:
            yield chunk


class ClosingFailingAsyncStream:
    def __init__(self) -> None:
        self._yielded = False

    def __aiter__(self) -> ClosingFailingAsyncStream:
        return self

    async def __anext__(self) -> object:
        if not self._yielded:
            self._yielded = True
            return ("values", {"partial": True})
        raise RuntimeError("astream failed")

    async def aclose(self) -> None:
        raise RuntimeError("aclose failed")


class ClosingFailingAsyncGraph:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def astream(
        self,
        input: object,
        *,
        config: dict[str, object],
        version: str,
        stream_mode: list[str],
    ) -> ClosingFailingAsyncStream:
        self.calls.append(
            {
                "input": input,
                "config": config,
                "version": version,
                "stream_mode": stream_mode,
            }
        )
        return ClosingFailingAsyncStream()


class BlockingAsyncGraph:
    def __init__(self) -> None:
        self.after_first_chunk = asyncio.Event()
        self.never = asyncio.Event()

    async def astream(
        self,
        input: object,
        *,
        config: dict[str, object],
        version: str,
        stream_mode: list[str],
    ) -> AsyncIterator[object]:
        del input, config, version, stream_mode
        yield ("values", {"partial": True})
        self.after_first_chunk.set()
        await self.never.wait()


def reload_invoke_with_fake_langgraph(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    langgraph_module = ModuleType("langgraph")
    callbacks_module = ModuleType("langgraph.callbacks")
    callbacks_module.GraphCallbackHandler = FakeGraphCallbackHandler
    monkeypatch.setitem(sys.modules, "langgraph", langgraph_module)
    monkeypatch.setitem(sys.modules, "langgraph.callbacks", callbacks_module)

    import opscanvas_langgraph.callbacks as callbacks
    import opscanvas_langgraph.invoke as invoke

    importlib.reload(callbacks)
    return importlib.reload(invoke)


def reload_package_without_langgraph(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    langgraph_module = ModuleType("langgraph")
    monkeypatch.setitem(sys.modules, "langgraph", langgraph_module)
    monkeypatch.delitem(sys.modules, "langgraph.callbacks", raising=False)

    import opscanvas_langgraph as package
    import opscanvas_langgraph.callbacks as callbacks
    import opscanvas_langgraph.invoke as invoke

    importlib.reload(callbacks)
    importlib.reload(invoke)
    return importlib.reload(package)


def callback_handler_class() -> type[object]:
    callbacks = importlib.import_module("opscanvas_langgraph.callbacks")
    return callbacks.OpsCanvasGraphCallbackHandler


def test_traced_invoke_passes_public_stream_arguments_and_returns_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invoke = reload_invoke_with_fake_langgraph(monkeypatch)
    exporter = OpsCanvasExporter()
    graph = FakeSyncGraph(
        [
            ("tasks", {"id": "task-1", "name": "node", "input": {"x": 1}}),
            ("values", {"step": 1}),
            (("subgraph",), "values", {"answer": 42}),
            {"type": "messages", "data": "hello"},
        ]
    )
    original_config: dict[str, object] = {"configurable": {"thread_id": "thread-1"}}

    result = invoke.traced_invoke(
        graph,
        {"question": "hi"},
        config=original_config,
        exporter=exporter,
        run_id="run_sync",
    )

    assert result == {"answer": 42}
    assert graph.calls == [
        {
            "input": {"question": "hi"},
            "config": graph.calls[0]["config"],
            "version": "v2",
            "stream_mode": ["tasks", "checkpoints", "messages", "values"],
        }
    ]
    effective_config = graph.calls[0]["config"]
    assert effective_config is not original_config
    assert effective_config["configurable"] is original_config["configurable"]
    assert "callbacks" not in original_config
    assert isinstance(effective_config["callbacks"][0], callback_handler_class())
    assert len(exporter.runs) == 1
    assert exporter.runs[0].status is RunStatus.succeeded
    assert exporter.runs[0].workflow_name == "Fake graph"


def test_traced_invoke_preserves_callback_order_without_mutating_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invoke = reload_invoke_with_fake_langgraph(monkeypatch)
    graph = FakeSyncGraph([("values", {"ok": True})])
    existing_callback = object()
    original_callbacks = [existing_callback]
    original_config: dict[str, object] = {"callbacks": original_callbacks, "recursion_limit": 5}

    invoke.traced_invoke(graph, {}, config=original_config, run_id="run_callbacks")

    effective_callbacks = graph.calls[0]["config"]["callbacks"]
    assert effective_callbacks[:1] == [existing_callback]
    assert isinstance(effective_callbacks[1], callback_handler_class())
    assert original_config["callbacks"] is original_callbacks
    assert original_callbacks == [existing_callback]


def test_traced_invoke_accepts_single_stream_mode_string(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invoke = reload_invoke_with_fake_langgraph(monkeypatch)
    graph = FakeSyncGraph([("values", {"ok": True})])

    result = invoke.traced_invoke(graph, {}, run_id="run_string_mode", stream_modes="values")

    assert result == {"ok": True}
    assert graph.calls[0]["stream_mode"] == ["values"]


def test_traced_invoke_falls_back_to_last_non_task_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invoke = reload_invoke_with_fake_langgraph(monkeypatch)
    graph = FakeSyncGraph(
        [
            ("tasks", {"id": "task-1", "name": "node", "input": None}),
            ("messages", {"content": "ignored after fallback"}),
            {"final": "plain"},
        ]
    )

    result = invoke.traced_invoke(graph, {}, run_id="run_fallback")

    assert result == {"final": "plain"}


def test_traced_invoke_exports_failed_run_and_reraises_stream_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invoke = reload_invoke_with_fake_langgraph(monkeypatch)
    exporter = OpsCanvasExporter()

    with pytest.raises(RuntimeError, match="stream failed"):
        invoke.traced_invoke(FailingSyncGraph(), {}, exporter=exporter, run_id="run_failed")

    assert len(exporter.runs) == 1
    assert exporter.runs[0].status is RunStatus.failed
    assert exporter.runs[0].metadata["langgraph.error"] == {
        "type": "RuntimeError",
        "has_error": True,
    }


def test_traced_invoke_suppresses_close_error_after_stream_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invoke = reload_invoke_with_fake_langgraph(monkeypatch)
    exporter = OpsCanvasExporter()

    with pytest.raises(RuntimeError, match="stream failed"):
        invoke.traced_invoke(
            ClosingFailingSyncGraph(),
            {},
            exporter=exporter,
            run_id="run_close_failed",
        )

    assert len(exporter.runs) == 1
    assert exporter.runs[0].status is RunStatus.failed
    assert exporter.runs[0].metadata["langgraph.error"] == {
        "type": "RuntimeError",
        "has_error": True,
    }


def test_traced_ainvoke_passes_public_stream_arguments_and_returns_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invoke = reload_invoke_with_fake_langgraph(monkeypatch)
    exporter = OpsCanvasExporter()
    graph = FakeAsyncGraph([("updates", {"node": {"x": 1}}), ("values", {"answer": 7})])

    result = asyncio.run(
        invoke.traced_ainvoke(
            graph,
            {"question": "hi"},
            exporter=exporter,
            run_id="run_async",
            stream_modes=["values", "messages"],
        )
    )

    assert result == {"answer": 7}
    assert graph.calls[0]["input"] == {"question": "hi"}
    assert graph.calls[0]["version"] == "v2"
    assert graph.calls[0]["stream_mode"] == ["values", "messages"]
    assert isinstance(
        graph.calls[0]["config"]["callbacks"][0],
        callback_handler_class(),
    )
    assert len(exporter.runs) == 1
    assert exporter.runs[0].status is RunStatus.succeeded
    assert exporter.runs[0].workflow_name == "Async graph"


def test_traced_ainvoke_suppresses_aclose_error_after_stream_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invoke = reload_invoke_with_fake_langgraph(monkeypatch)
    exporter = OpsCanvasExporter()

    async def run() -> None:
        with pytest.raises(RuntimeError, match="astream failed"):
            await invoke.traced_ainvoke(
                ClosingFailingAsyncGraph(),
                {},
                exporter=exporter,
                run_id="run_aclose_failed",
            )

    asyncio.run(run())

    assert len(exporter.runs) == 1
    assert exporter.runs[0].status is RunStatus.failed
    assert exporter.runs[0].metadata["langgraph.error"] == {
        "type": "RuntimeError",
        "has_error": True,
    }


def test_traced_ainvoke_cancellation_exports_interrupted_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invoke = reload_invoke_with_fake_langgraph(monkeypatch)
    exporter = OpsCanvasExporter()

    async def cancel_after_first_chunk() -> None:
        graph = BlockingAsyncGraph()
        task = asyncio.create_task(
            invoke.traced_ainvoke(graph, {}, exporter=exporter, run_id="run_cancelled")
        )
        await graph.after_first_chunk.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(cancel_after_first_chunk())

    assert len(exporter.runs) == 1
    assert exporter.runs[0].status is RunStatus.interrupted
    assert exporter.runs[0].metadata["langgraph.interrupt_reason"] == {
        "type": "str",
        "length": 9,
    }


def test_package_import_still_works_without_langgraph(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = reload_package_without_langgraph(monkeypatch)

    assert callable(package.traced_invoke)
    assert callable(package.traced_ainvoke)


def test_traced_invoke_without_langgraph_raises_when_callbacks_are_needed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = reload_package_without_langgraph(monkeypatch)
    exporter = OpsCanvasExporter()

    with pytest.raises(RuntimeError, match="opscanvas-langgraph\\[langgraph\\]"):
        package.traced_invoke(FakeSyncGraph([]), {}, exporter=exporter, run_id="run_missing")

    assert len(exporter.runs) == 1
    assert exporter.runs[0].status is RunStatus.failed
