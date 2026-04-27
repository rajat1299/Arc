#!/usr/bin/env python3
"""Prove local ClickHouse-backed API persistence across an API process restart."""

from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import time
from collections.abc import Mapping
from typing import Any

try:
    from smoke_ingest import (
        DEFAULT_WEB_URL,
        EXPECTED_SPAN_KINDS,
        SmokeError,
        request_json,
        require,
        require_rich_spans,
        run_smoke,
    )
except ModuleNotFoundError:
    from scripts.smoke_ingest import (
        DEFAULT_WEB_URL,
        EXPECTED_SPAN_KINDS,
        SmokeError,
        request_json,
        require,
        require_rich_spans,
        run_smoke,
    )


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 18080


def is_port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.25)
        return sock.connect_ex((host, port)) == 0


def start_api(
    *,
    host: str,
    port: int,
    clickhouse_host: str,
    clickhouse_port: int,
    clickhouse_username: str,
    clickhouse_password: str,
    clickhouse_database: str,
    clickhouse_secure: bool,
) -> subprocess.Popen[str]:
    env = os.environ.copy()
    env.update(
        {
            "OPSCANVAS_API_STORE_BACKEND": "clickhouse",
            "OPSCANVAS_API_CLICKHOUSE_HOST": clickhouse_host,
            "OPSCANVAS_API_CLICKHOUSE_PORT": str(clickhouse_port),
            "OPSCANVAS_API_CLICKHOUSE_USERNAME": clickhouse_username,
            "OPSCANVAS_API_CLICKHOUSE_PASSWORD": clickhouse_password,
            "OPSCANVAS_API_CLICKHOUSE_DATABASE": clickhouse_database,
            "OPSCANVAS_API_CLICKHOUSE_SECURE": str(clickhouse_secure).lower(),
        }
    )
    return subprocess.Popen(
        [
            "uv",
            "run",
            "--with",
            "uvicorn",
            "--package",
            "opscanvas-api",
            "python",
            "-m",
            "uvicorn",
            "opscanvas_api.app:app",
            "--app-dir",
            "services/api/src",
            "--host",
            host,
            "--port",
            str(port),
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def stop_api(process: subprocess.Popen[str], *, timeout: float = 10.0) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=timeout)


def wait_for_api(process: subprocess.Popen[str], api_url: str, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    last_error: str | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            stdout, stderr = process.communicate()
            output = "\n".join(part for part in (stdout, stderr) if part)
            raise SmokeError(f"API process exited before becoming healthy:\n{output}")
        try:
            health = request_json("GET", api_url, "/healthz", timeout=min(1.0, timeout))
            if health.status == 200:
                return
        except SmokeError as error:
            last_error = str(error)
        time.sleep(0.25)
    raise SmokeError(f"API did not become healthy at {api_url} within {timeout:g}s: {last_error}")


def verify_persisted_run(api_url: str, timeout: float, run_id: str) -> None:
    runs = request_json("GET", api_url, "/v1/runs", timeout=timeout)
    require(runs.status == 200, f"Expected run list status 200 after restart, got {runs.status}")
    require(isinstance(runs.body, list), "Expected restarted run list response to be a JSON array")
    require(
        any(run.get("id") == run_id for run in runs.body if isinstance(run, dict)),
        "Persisted run missing from /v1/runs after API restart",
    )
    print(f"After restart: GET /v1/runs -> {runs.status} found {run_id}")

    run = request_json("GET", api_url, f"/v1/runs/{run_id}", timeout=timeout)
    require(run.status == 200, f"Expected run detail status 200 after restart, got {run.status}")
    require(isinstance(run.body, dict), "Expected restarted run detail to be a JSON object")
    require(run.body.get("id") == run_id, "Restarted run detail returned the wrong run")
    require_rich_spans(run.body.get("spans"), run_id, "Restarted run detail")
    print(
        f"After restart: GET /v1/runs/{run_id} -> {run.status} "
        f"returned {len(EXPECTED_SPAN_KINDS)} spans"
    )

    spans = request_json("GET", api_url, f"/v1/runs/{run_id}/spans", timeout=timeout)
    require(spans.status == 200, f"Expected run spans status 200 after restart, got {spans.status}")
    require_rich_spans(spans.body, run_id, "Restarted run spans endpoint")
    print(
        f"After restart: GET /v1/runs/{run_id}/spans -> {spans.status} "
        f"returned {len(EXPECTED_SPAN_KINDS)} spans"
    )

    metrics = request_json("GET", api_url, "/v1/runs/metrics", timeout=timeout)
    require(
        metrics.status == 200,
        f"Expected metrics status 200 after restart, got {metrics.status}",
    )
    require(isinstance(metrics.body, dict), "Expected restarted metrics response to be an object")
    require(metrics.body.get("run_count", 0) >= 1, "Restarted metrics omitted persisted runs")
    print(f"After restart: GET /v1/runs/metrics -> {metrics.status} includes persisted runs")


def run_persistence_smoke(
    *,
    host: str,
    port: int,
    timeout: float,
    run_id: str | None,
    web_url: str,
    clickhouse_host: str,
    clickhouse_port: int,
    clickhouse_username: str,
    clickhouse_password: str,
    clickhouse_database: str,
    clickhouse_secure: bool,
) -> None:
    if is_port_open(host, port):
        raise SmokeError(
            f"API smoke port {host}:{port} is already in use. "
            "Choose another --port so the smoke does not clobber an existing API."
        )

    api_url = f"http://{host}:{port}"
    run_id = run_id or f"run_clickhouse_smoke_{int(time.time())}"
    api_kwargs: Mapping[str, Any] = {
        "host": host,
        "port": port,
        "clickhouse_host": clickhouse_host,
        "clickhouse_port": clickhouse_port,
        "clickhouse_username": clickhouse_username,
        "clickhouse_password": clickhouse_password,
        "clickhouse_database": clickhouse_database,
        "clickhouse_secure": clickhouse_secure,
    }

    print(f"Starting ClickHouse-mode API on {api_url}")
    first_process = start_api(**api_kwargs)
    try:
        wait_for_api(first_process, api_url, timeout)
        run_smoke(api_url=api_url, timeout=timeout, run_id=run_id, web_url=web_url)
    finally:
        stop_api(first_process)

    if is_port_open(host, port):
        raise SmokeError(f"API smoke port {host}:{port} remained occupied after shutdown")

    print("Restarting ClickHouse-mode API to verify persisted run")
    second_process = start_api(**api_kwargs)
    try:
        wait_for_api(second_process, api_url, timeout)
        verify_persisted_run(api_url, timeout, run_id)
    finally:
        stop_api(second_process)

    print("ClickHouse persistence smoke passed")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Start a local OpsCanvas API in ClickHouse mode, ingest the rich smoke fixture, "
            "restart the API, and verify the same run is still queryable."
        )
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help=f"API host. Defaults to {DEFAULT_HOST}.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"API port. Defaults to {DEFAULT_PORT}.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=15.0,
        help="Startup/request timeout seconds.",
    )
    parser.add_argument("--run-id", help="Optional deterministic run ID.")
    parser.add_argument(
        "--web-url",
        default=DEFAULT_WEB_URL,
        help=f"Base URL for printed web link. Defaults to {DEFAULT_WEB_URL}.",
    )
    parser.add_argument("--clickhouse-host", default="127.0.0.1")
    parser.add_argument("--clickhouse-port", type=int, default=8123)
    parser.add_argument("--clickhouse-username", default="opscanvas")
    parser.add_argument("--clickhouse-password", default="opscanvas_dev_password")
    parser.add_argument("--clickhouse-database", default="opscanvas")
    parser.add_argument("--clickhouse-secure", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        run_persistence_smoke(
            host=args.host,
            port=args.port,
            timeout=args.timeout,
            run_id=args.run_id,
            web_url=args.web_url,
            clickhouse_host=args.clickhouse_host,
            clickhouse_port=args.clickhouse_port,
            clickhouse_username=args.clickhouse_username,
            clickhouse_password=args.clickhouse_password,
            clickhouse_database=args.clickhouse_database,
            clickhouse_secure=args.clickhouse_secure,
        )
    except SmokeError as error:
        print(f"ClickHouse persistence smoke failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
