from datetime import UTC, datetime

import httpx
import pytest
from opscanvas_claude import (
    OpsCanvasClient,
    OpsCanvasClientError,
    OpsCanvasConfig,
    OpsCanvasExporter,
)
from opscanvas_core import Run, RunStatus, Span, SpanKind


def _run(status: RunStatus = RunStatus.succeeded) -> Run:
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    return Run(
        id="run_123",
        status=status,
        started_at=timestamp,
        ended_at=timestamp,
        runtime="claude-agent-sdk",
        spans=[
            Span(
                id="span_123",
                run_id="run_123",
                kind=SpanKind.agent,
                name="claude query",
                started_at=timestamp,
                input={"prompt": "hi"},
                output={"text": "hello"},
            )
        ],
    )


def test_client_posts_run_json_payload_with_aliases_and_bearer_auth() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(202, json={"ok": True})

    client = OpsCanvasClient(
        endpoint="https://api.example.test/",
        api_key="key_123",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    client.ingest_run(_run())

    assert len(requests) == 1
    request = requests[0]
    assert request.method == "POST"
    assert str(request.url) == "https://api.example.test/v1/ingest/runs"
    assert request.headers["authorization"] == "Bearer key_123"
    assert request.headers["content-type"] == "application/json"
    payload = request.read()
    assert b'"input"' in payload
    assert b'"output"' in payload
    assert b'"input_data"' not in payload
    assert b'"output_data"' not in payload


def test_client_omits_bearer_header_without_api_key() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(204)

    client = OpsCanvasClient(
        endpoint="https://api.example.test",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    client.ingest_run(_run())

    assert "authorization" not in requests[0].headers


def test_client_raises_clear_error_for_missing_endpoint() -> None:
    with pytest.raises(ValueError, match="OpsCanvas endpoint is required"):
        OpsCanvasClient(config=OpsCanvasConfig(endpoint=None))


def test_client_raises_sanitized_error_for_non_success_response() -> None:
    response_body = '{"error":"rejected","secret":"sk_live_secret","input":"private prompt"}'
    client = OpsCanvasClient(
        endpoint="https://api.example.test",
        http_client=httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(500, text=response_body)
            )
        ),
    )

    with pytest.raises(OpsCanvasClientError) as exc_info:
        client.ingest_run(_run(RunStatus.failed))

    message = str(exc_info.value)
    assert "500" in message
    assert "Internal Server Error" in message
    assert "private prompt" not in message
    assert "sk_live_secret" not in message
    assert response_body not in message


class RecordingClient:
    def __init__(self) -> None:
        self.runs: list[Run] = []

    def ingest_run(self, run: Run) -> None:
        self.runs.append(run)


def test_exporter_records_spans_and_completed_runs() -> None:
    exporter = OpsCanvasExporter(config=OpsCanvasConfig())
    span = _run().spans[0]
    run = _run()

    exporter.export([span])
    exporter.export_run(run)

    assert exporter.spans == [span]
    assert exporter.runs == [run]


def test_exporter_respects_shutdown() -> None:
    exporter = OpsCanvasExporter(config=OpsCanvasConfig())
    span = _run().spans[0]
    run = _run()

    exporter.shutdown()
    exporter.export([span])
    exporter.export_run(run)

    assert exporter.spans == []
    assert exporter.runs == []


def test_exporter_sends_runs_only_when_enabled() -> None:
    recording_client = RecordingClient()
    run = _run()
    disabled = OpsCanvasExporter(
        config=OpsCanvasConfig(),
        client=recording_client,
        send_runs=False,
    )
    enabled = OpsCanvasExporter(
        config=OpsCanvasConfig(),
        client=recording_client,
        send_runs=True,
    )

    disabled.export_run(run)
    assert recording_client.runs == []

    enabled.export_run(run)
    assert recording_client.runs == [run]
