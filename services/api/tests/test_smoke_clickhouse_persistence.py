from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts import smoke_clickhouse_persistence


class FakeProcess:
    def __init__(self) -> None:
        self.terminated = False
        self.waited = False
        self.killed = False
        self.returncode: int | None = None

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = 0

    def wait(self, timeout: float | None = None) -> int:
        self.waited = True
        return self.returncode or 0

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9

    def communicate(self) -> tuple[str, str]:
        return ("", "")


def test_run_persistence_smoke_restarts_api_with_clickhouse_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    processes = [FakeProcess(), FakeProcess()]
    popen_calls: list[dict[str, Any]] = []
    smoke_calls: list[tuple[str, str]] = []
    verify_calls: list[tuple[str, str]] = []

    def fake_popen(command: list[str], **kwargs: Any) -> FakeProcess:
        popen_calls.append({"command": command, **kwargs})
        return processes[len(popen_calls) - 1]

    monkeypatch.setattr(smoke_clickhouse_persistence, "is_port_open", lambda *_: False)
    monkeypatch.setattr(smoke_clickhouse_persistence.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(smoke_clickhouse_persistence, "wait_for_api", lambda *_: None)
    monkeypatch.setattr(
        smoke_clickhouse_persistence,
        "run_smoke",
        lambda api_url, timeout, run_id, web_url: smoke_calls.append((api_url, run_id or "")),
    )
    monkeypatch.setattr(
        smoke_clickhouse_persistence,
        "verify_persisted_run",
        lambda api_url, timeout, run_id: verify_calls.append((api_url, run_id)),
    )

    smoke_clickhouse_persistence.run_persistence_smoke(
        host="127.0.0.1",
        port=18080,
        timeout=3.0,
        run_id="run_test",
        web_url="http://localhost:3000/",
        clickhouse_host="127.0.0.1",
        clickhouse_port=8123,
        clickhouse_username="opscanvas",
        clickhouse_password="secret",
        clickhouse_database="opscanvas",
        clickhouse_secure=False,
    )

    assert len(popen_calls) == 2
    assert smoke_calls == [("http://127.0.0.1:18080", "run_test")]
    assert verify_calls == [("http://127.0.0.1:18080", "run_test")]
    assert all(process.terminated and process.waited for process in processes)
    for call in popen_calls:
        env = call["env"]
        assert env["OPSCANVAS_API_STORE_BACKEND"] == "clickhouse"
        assert env["OPSCANVAS_API_CLICKHOUSE_PASSWORD"] == "secret"
        assert "--port" in call["command"]
        assert "18080" in call["command"]


def test_run_persistence_smoke_refuses_occupied_api_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(smoke_clickhouse_persistence, "is_port_open", lambda *_: True)

    with pytest.raises(smoke_clickhouse_persistence.SmokeError, match="already in use"):
        smoke_clickhouse_persistence.run_persistence_smoke(
            host="127.0.0.1",
            port=18080,
            timeout=3.0,
            run_id="run_test",
            web_url="http://localhost:3000/",
            clickhouse_host="127.0.0.1",
            clickhouse_port=8123,
            clickhouse_username="opscanvas",
            clickhouse_password="secret",
            clickhouse_database="opscanvas",
            clickhouse_secure=False,
        )
