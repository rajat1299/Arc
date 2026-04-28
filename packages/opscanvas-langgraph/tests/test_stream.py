from __future__ import annotations

import asyncio
import importlib
import re
import sys
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from types import ModuleType

import pytest
from opscanvas_core import RunStatus
from opscanvas_langgraph.exporter import OpsCanvasExporter


class FakeGraphCallbackHandler:
    def __init__(self) -> None:
        self.base_initialized = True


class FakeSyncGraph:
    name = "Sync stream graph"

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
        **kwargs: object,
    ) -> Iterator[object]:
        self.calls.append(
            {
                "input": input,
                "config": config,
                "version": version,
                "stream_mode": stream_mode,
                "kwargs": kwargs,
            }
        )
        yield from self.chunks


class FailingSyncGraph:
    def stream(
        self,
        input: object,
        *,
        config: dict[str, object],
        version: str,
        stream_mode: list[str],
        **kwargs: object,
    ) -> Iterator[object]:
        del input, config, version, stream_mode, kwargs
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
    def stream(
        self,
        input: object,
        *,
        config: dict[str, object],
        version: str,
        stream_mode: list[str],
        **kwargs: object,
    ) -> ClosingFailingSyncStream:
        del input, config, version, stream_mode, kwargs
        return ClosingFailingSyncStream()


class FakeAsyncGraph:
    name = "Async stream graph"

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
        **kwargs: object,
    ) -> AsyncIterator[object]:
        self.calls.append(
            {
                "input": input,
                "config": config,
                "version": version,
                "stream_mode": stream_mode,
                "kwargs": kwargs,
            }
        )
        for chunk in self.chunks:
            yield chunk


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
        **kwargs: object,
    ) -> AsyncIterator[object]:
        del input, config, version, stream_mode, kwargs
        yield ("values", {"partial": True})
        self.after_first_chunk.set()
        await self.never.wait()


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
    def astream(
        self,
        input: object,
        *,
        config: dict[str, object],
        version: str,
        stream_mode: list[str],
        **kwargs: object,
    ) -> ClosingFailingAsyncStream:
        del input, config, version, stream_mode, kwargs
        return ClosingFailingAsyncStream()


def reload_stream_with_fake_langgraph(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    langgraph_module = ModuleType("langgraph")
    callbacks_module = ModuleType("langgraph.callbacks")
    callbacks_module.GraphCallbackHandler = FakeGraphCallbackHandler
    monkeypatch.setitem(sys.modules, "langgraph", langgraph_module)
    monkeypatch.setitem(sys.modules, "langgraph.callbacks", callbacks_module)

    import opscanvas_langgraph.callbacks as callbacks
    import opscanvas_langgraph.stream as stream

    importlib.reload(callbacks)
    return importlib.reload(stream)


def reload_package_without_langgraph(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    langgraph_module = ModuleType("langgraph")
    monkeypatch.setitem(sys.modules, "langgraph", langgraph_module)
    monkeypatch.delitem(sys.modules, "langgraph.callbacks", raising=False)

    import opscanvas_langgraph as package
    import opscanvas_langgraph.callbacks as callbacks
    import opscanvas_langgraph.stream as stream

    importlib.reload(callbacks)
    importlib.reload(stream)
    return importlib.reload(package)


def callback_handler_class() -> type[object]:
    callbacks = importlib.import_module("opscanvas_langgraph.callbacks")
    return callbacks.OpsCanvasGraphCallbackHandler


def test_traced_stream_yields_chunks_unchanged_and_exports_completed_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stream = reload_stream_with_fake_langgraph(monkeypatch)
    exporter = OpsCanvasExporter()
    chunks = [
        ("tasks", {"id": "task-1", "name": "node", "input": {"x": 1}}),
        ("values", {"answer": 42}),
        (("subgraph",), "messages", "hello"),
    ]
    graph = FakeSyncGraph(chunks)
    original_callbacks = [object()]
    original_config: dict[str, object] = {
        "callbacks": original_callbacks,
        "configurable": {"thread_id": "thread-1"},
    }

    result = list(
        stream.traced_stream(
            graph,
            {"question": "hi"},
            config=original_config,
            exporter=exporter,
            run_id="run_stream",
            stream_modes="values",
            subgraphs=True,
            interrupt_before=["node"],
            interrupt_after=["node"],
            debug=True,
            durability="sync",
        )
    )

    assert result == chunks
    assert graph.calls[0]["input"] == {"question": "hi"}
    assert graph.calls[0]["version"] == "v2"
    assert graph.calls[0]["stream_mode"] == ["values"]
    assert graph.calls[0]["kwargs"] == {
        "subgraphs": True,
        "interrupt_before": ["node"],
        "interrupt_after": ["node"],
        "debug": True,
        "durability": "sync",
    }
    effective_config = graph.calls[0]["config"]
    assert effective_config is not original_config
    assert effective_config["configurable"] is original_config["configurable"]
    assert effective_config["callbacks"][:1] == original_callbacks
    assert isinstance(effective_config["callbacks"][1], callback_handler_class())
    assert original_config["callbacks"] is original_callbacks
    assert len(exporter.runs) == 1
    assert exporter.runs[0].status is RunStatus.succeeded
    assert exporter.runs[0].workflow_name == "Sync stream graph"


def test_traced_stream_close_exports_interrupted_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stream = reload_stream_with_fake_langgraph(monkeypatch)
    exporter = OpsCanvasExporter()
    generator = stream.traced_stream(
        FakeSyncGraph([("values", {"partial": True}), ("values", {"done": True})]),
        {},
        exporter=exporter,
        run_id="run_closed",
    )

    assert next(generator) == ("values", {"partial": True})
    generator.close()

    assert len(exporter.runs) == 1
    assert exporter.runs[0].status is RunStatus.interrupted
    assert exporter.runs[0].metadata["langgraph.interrupt_reason"] == {
        "type": "str",
        "length": 15,
    }


def test_traced_stream_exception_exports_failed_run_and_reraises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stream = reload_stream_with_fake_langgraph(monkeypatch)
    exporter = OpsCanvasExporter()

    with pytest.raises(RuntimeError, match="stream failed"):
        list(stream.traced_stream(FailingSyncGraph(), {}, exporter=exporter, run_id="run_failed"))

    assert len(exporter.runs) == 1
    assert exporter.runs[0].status is RunStatus.failed
    assert exporter.runs[0].metadata["langgraph.error"] == {
        "type": "RuntimeError",
        "has_error": True,
    }


def test_traced_stream_suppresses_close_error_after_stream_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stream = reload_stream_with_fake_langgraph(monkeypatch)
    exporter = OpsCanvasExporter()

    with pytest.raises(RuntimeError, match="stream failed"):
        list(
            stream.traced_stream(
                ClosingFailingSyncGraph(),
                {},
                exporter=exporter,
                run_id="run_close_failed",
            )
        )

    assert len(exporter.runs) == 1
    assert exporter.runs[0].status is RunStatus.failed


def test_traced_stream_rejects_reserved_kwargs(monkeypatch: pytest.MonkeyPatch) -> None:
    stream = reload_stream_with_fake_langgraph(monkeypatch)
    generator = stream.traced_stream(FakeSyncGraph([]), {}, version="v1")

    with pytest.raises(TypeError, match="version"):
        next(generator)


def test_traced_astream_yields_chunks_unchanged_and_exports_completed_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stream = reload_stream_with_fake_langgraph(monkeypatch)
    exporter = OpsCanvasExporter()
    chunks = [("updates", {"node": {"x": 1}}), ("values", {"answer": 7})]
    graph = FakeAsyncGraph(chunks)

    async def run() -> list[object]:
        result = []
        async for chunk in stream.traced_astream(
            graph,
            {"question": "hi"},
            exporter=exporter,
            run_id="run_astream",
            stream_modes=["values", "messages"],
            subgraphs=True,
        ):
            result.append(chunk)
        return result

    assert asyncio.run(run()) == chunks
    assert graph.calls[0]["input"] == {"question": "hi"}
    assert graph.calls[0]["version"] == "v2"
    assert graph.calls[0]["stream_mode"] == ["values", "messages"]
    assert graph.calls[0]["kwargs"] == {"subgraphs": True}
    assert len(exporter.runs) == 1
    assert exporter.runs[0].status is RunStatus.succeeded
    assert exporter.runs[0].workflow_name == "Async stream graph"


def test_traced_astream_cancellation_exports_interrupted_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stream = reload_stream_with_fake_langgraph(monkeypatch)
    exporter = OpsCanvasExporter()

    async def cancel_after_first_chunk() -> None:
        graph = BlockingAsyncGraph()

        async def consume() -> None:
            async for _chunk in stream.traced_astream(
                graph,
                {},
                exporter=exporter,
                run_id="run_cancelled",
            ):
                pass

        task = asyncio.create_task(consume())
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


def test_traced_astream_suppresses_aclose_error_after_stream_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stream = reload_stream_with_fake_langgraph(monkeypatch)
    exporter = OpsCanvasExporter()

    async def run() -> None:
        with pytest.raises(RuntimeError, match="astream failed"):
            async for _chunk in stream.traced_astream(
                ClosingFailingAsyncGraph(),
                {},
                exporter=exporter,
                run_id="run_aclose_failed",
            ):
                pass

    asyncio.run(run())

    assert len(exporter.runs) == 1
    assert exporter.runs[0].status is RunStatus.failed


def test_package_import_still_works_without_langgraph(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = reload_package_without_langgraph(monkeypatch)

    assert callable(package.traced_stream)
    assert callable(package.traced_astream)


def test_readme_examples_refer_to_exported_symbols() -> None:
    import opscanvas_langgraph

    readme = Path("packages/opscanvas-langgraph/README.md").read_text()
    imported_names = set()
    for match in re.finditer(r"from opscanvas_langgraph import ([^\n]+)", readme):
        imported_names.update(name.strip() for name in match.group(1).split(","))

    assert {
        "LangGraphRunRecorder",
        "merge_opscanvas_callbacks",
        "traced_ainvoke",
        "traced_astream",
        "traced_invoke",
        "traced_stream",
    }.issubset(imported_names)
    assert imported_names.issubset(set(opscanvas_langgraph.__all__))
