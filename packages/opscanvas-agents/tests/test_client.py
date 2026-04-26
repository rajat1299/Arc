from datetime import UTC, datetime

import httpx
import pytest
from opscanvas_agents import OpsCanvasClient, OpsCanvasClientError
from opscanvas_core import Run, RunStatus, Span, SpanKind


def test_client_posts_run_json_payload_with_aliases() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(202, json={"ok": True})

    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=transport)
    client = OpsCanvasClient(
        endpoint="https://api.example.test/",
        api_key="key_123",
        http_client=http_client,
    )
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    run = Run(
        id="run_123",
        status=RunStatus.succeeded,
        started_at=timestamp,
        ended_at=timestamp,
        runtime="openai-agents",
        spans=[
            Span(
                id="span_123",
                run_id="run_123",
                kind=SpanKind.model_call,
                name="gpt-5.1",
                started_at=timestamp,
                input={"prompt": "hi"},
                output={"text": "hello"},
            )
        ],
    )

    client.ingest_run(run)

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


def test_client_raises_clear_error_for_non_success_response() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(500, text="boom"))
    http_client = httpx.Client(transport=transport)
    client = OpsCanvasClient(endpoint="https://api.example.test", http_client=http_client)
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    run = Run(
        id="run_123",
        status=RunStatus.failed,
        started_at=timestamp,
        runtime="openai-agents",
    )

    with pytest.raises(OpsCanvasClientError, match="500.*boom"):
        client.ingest_run(run)
