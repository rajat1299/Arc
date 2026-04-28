from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass
from types import ModuleType
from typing import Any

import pytest
from opscanvas_core import RunStatus
from opscanvas_langgraph import LangGraphRunRecorder


@dataclass
class FakeInterruptEvent:
    reason: str
    value: dict[str, Any]


@dataclass
class FakeResumeEvent:
    value: dict[str, Any]
    config: dict[str, Any]


class FakeGraphCallbackHandler:
    def __init__(self) -> None:
        self.base_initialized = True


class FakeCallbackManager:
    def __init__(self, handlers: list[object]) -> None:
        self.handlers = handlers
        self.added: list[tuple[object, bool]] = []

    def __copy__(self) -> FakeCallbackManager:
        copied = FakeCallbackManager(self.handlers)
        copied.added = self.added
        return copied

    def copy(self) -> FakeCallbackManager:
        copied = FakeCallbackManager(list(self.handlers))
        copied.added = list(self.added)
        return copied

    def add_handler(self, handler: object, *, inherit: bool = True) -> None:
        self.added.append((handler, inherit))
        self.handlers.append(handler)


def reload_callbacks_with_fake_langgraph(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    langgraph_module = ModuleType("langgraph")
    callbacks_module = ModuleType("langgraph.callbacks")
    callbacks_module.GraphCallbackHandler = FakeGraphCallbackHandler
    monkeypatch.setitem(sys.modules, "langgraph", langgraph_module)
    monkeypatch.setitem(sys.modules, "langgraph.callbacks", callbacks_module)

    import opscanvas_langgraph.callbacks as callbacks

    return importlib.reload(callbacks)


def reload_callbacks_without_langgraph(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    langgraph_module = ModuleType("langgraph")
    monkeypatch.setitem(sys.modules, "langgraph", langgraph_module)
    monkeypatch.delitem(sys.modules, "langgraph.callbacks", raising=False)

    import opscanvas_langgraph.callbacks as callbacks

    return importlib.reload(callbacks)


def test_package_import_works_without_langgraph(monkeypatch: pytest.MonkeyPatch) -> None:
    callbacks = reload_callbacks_without_langgraph(monkeypatch)

    package = importlib.import_module("opscanvas_langgraph")

    assert package.LangGraphRunRecorder is LangGraphRunRecorder
    with pytest.raises(RuntimeError) as exc_info:
        callbacks.OpsCanvasGraphCallbackHandler(object())
    assert callbacks.get_langgraph_install_error() == str(exc_info.value)


def test_missing_langgraph_raises_only_when_constructing_handler_or_merging(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    callbacks = reload_callbacks_without_langgraph(monkeypatch)
    recorder = LangGraphRunRecorder(run_id="run_missing_langgraph")

    with pytest.raises(RuntimeError, match="opscanvas-langgraph\\[langgraph\\]"):
        callbacks.OpsCanvasGraphCallbackHandler(recorder)

    with pytest.raises(RuntimeError, match="opscanvas-langgraph\\[langgraph\\]"):
        callbacks.merge_opscanvas_callbacks({}, recorder)


def test_handler_subclasses_langgraph_base_and_records_interrupt_resume(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    callbacks = reload_callbacks_with_fake_langgraph(monkeypatch)
    recorder = LangGraphRunRecorder(run_id="run_callbacks")

    handler = callbacks.OpsCanvasGraphCallbackHandler(recorder)
    handler.on_interrupt(FakeInterruptEvent(reason="approval", value={"secret": "pause"}))
    handler.on_resume(FakeResumeEvent(value={"secret": "resume"}, config={"x": 1}))
    run = recorder.finish()

    assert isinstance(handler, FakeGraphCallbackHandler)
    assert handler.base_initialized is True
    assert run.status is RunStatus.interrupted
    assert [event.name for event in run.spans[0].events] == [
        "langgraph.interrupt",
        "langgraph.resume",
    ]
    assert run.spans[0].events[0].attributes["event_type"] == "FakeInterruptEvent"
    assert run.spans[0].events[1].attributes["event_type"] == "FakeResumeEvent"


def test_merge_without_callbacks_preserves_config_and_adds_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    callbacks = reload_callbacks_with_fake_langgraph(monkeypatch)
    recorder = LangGraphRunRecorder(run_id="run_no_callbacks")
    original = {"configurable": {"thread_id": "thread_123"}}

    merged = callbacks.merge_opscanvas_callbacks(original, recorder)

    assert merged is not original
    assert merged["configurable"] is original["configurable"]
    assert "callbacks" not in original
    assert len(merged["callbacks"]) == 1
    assert isinstance(merged["callbacks"][0], callbacks.OpsCanvasGraphCallbackHandler)


def test_merge_preserves_callback_order_for_single_list_and_tuple(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    callbacks = reload_callbacks_with_fake_langgraph(monkeypatch)
    first = object()
    second = object()
    existing_list = [first, second]

    single = callbacks.merge_opscanvas_callbacks(
        {"callbacks": first},
        LangGraphRunRecorder(run_id="run_single_callback"),
    )
    as_list = callbacks.merge_opscanvas_callbacks(
        {"callbacks": existing_list},
        LangGraphRunRecorder(run_id="run_list_callbacks"),
    )
    existing_tuple = (first, second)
    as_tuple = callbacks.merge_opscanvas_callbacks(
        {"callbacks": existing_tuple},
        LangGraphRunRecorder(run_id="run_tuple_callbacks"),
    )

    assert single["callbacks"][:1] == [first]
    assert isinstance(single["callbacks"][1], callbacks.OpsCanvasGraphCallbackHandler)
    assert as_list["callbacks"][:2] == [first, second]
    assert as_list["callbacks"] is not existing_list
    assert isinstance(as_list["callbacks"][2], callbacks.OpsCanvasGraphCallbackHandler)
    assert existing_list == [first, second]
    assert isinstance(as_tuple["callbacks"], list)
    assert as_tuple["callbacks"][:2] == list(existing_tuple)
    assert isinstance(as_tuple["callbacks"][2], callbacks.OpsCanvasGraphCallbackHandler)
    assert len(existing_tuple) == 2


def test_merge_copies_callback_manager_and_adds_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    callbacks = reload_callbacks_with_fake_langgraph(monkeypatch)
    existing = object()
    manager = FakeCallbackManager([existing])

    merged = callbacks.merge_opscanvas_callbacks(
        {"callbacks": manager, "recursion_limit": 3},
        LangGraphRunRecorder(run_id="run_manager_callbacks"),
    )

    copied = merged["callbacks"]
    assert copied is not manager
    assert isinstance(copied, FakeCallbackManager)
    assert copied.handlers[0] is existing
    assert isinstance(copied.handlers[1], callbacks.OpsCanvasGraphCallbackHandler)
    assert copied.added == [(copied.handlers[1], True)]
    assert manager.handlers == [existing]
    assert manager.added == []
    assert merged["recursion_limit"] == 3
