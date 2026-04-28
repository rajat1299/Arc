import json
from collections.abc import Mapping

import httpx
import pytest
from fastapi.testclient import TestClient
from opscanvas_api.app import create_app


class RecordingAsyncClient:
    def __init__(
        self,
        response: httpx.Response | None = None,
        exc: Exception | None = None,
    ) -> None:
        self.response = response
        self.exc = exc
        self.calls: list[dict[str, object]] = []

    async def post(
        self,
        url: str,
        *,
        json: Mapping[str, object],
        headers: Mapping[str, str],
    ) -> httpx.Response:
        self.calls.append({"url": url, "json": dict(json), "headers": dict(headers)})
        if self.exc is not None:
            raise self.exc
        assert self.response is not None
        return self.response


@pytest.fixture(autouse=True)
def proxy_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPSCANVAS_API_AUTH_ENABLED", raising=False)
    monkeypatch.delenv("OPSCANVAS_API_API_KEYS", raising=False)
    monkeypatch.delenv("OPSCANVAS_API_STORE_BACKEND", raising=False)
    monkeypatch.delenv("OPSCANVAS_API_OPENAI_PROXY_ENABLED", raising=False)
    monkeypatch.delenv("OPSCANVAS_API_OPENAI_UPSTREAM_API_KEY", raising=False)
    monkeypatch.setenv("OPSCANVAS_API_OPENAI_UPSTREAM_BASE_URL", "http://testserver/v1")


def test_disabled_proxy_route_returns_404() -> None:
    client = TestClient(create_app())

    response = client.post("/v1/chat/completions", json={"model": "gpt-5.4-mini"})

    assert response.status_code == 404


def test_disabled_proxy_trailing_slash_route_returns_404_not_redirect() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/v1/chat/completions/",
        json={"model": "gpt-5.4-mini"},
        follow_redirects=False,
    )

    assert response.status_code == 404
    assert "location" not in response.headers


def test_enabled_proxy_with_missing_upstream_key_returns_503_without_upstream_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPSCANVAS_API_OPENAI_PROXY_ENABLED", "true")
    app = create_app()
    upstream = RecordingAsyncClient(httpx.Response(200, json={"id": "chatcmpl_unused"}))
    app.state.openai_proxy_http_client = upstream
    client = TestClient(app)

    response = client.post("/v1/chat/completions", json={"model": "gpt-5.4-mini"})

    assert response.status_code == 503
    assert response.json() == {"detail": "OpenAI proxy upstream API key is not configured."}
    assert upstream.calls == []


def test_non_object_json_returns_422(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPSCANVAS_API_OPENAI_PROXY_ENABLED", "true")
    monkeypatch.setenv("OPSCANVAS_API_OPENAI_UPSTREAM_API_KEY", "sk-upstream-secret")
    app = create_app()
    upstream = RecordingAsyncClient(httpx.Response(200, json={"id": "chatcmpl_unused"}))
    app.state.openai_proxy_http_client = upstream
    client = TestClient(app)

    response = client.post("/v1/chat/completions", json=["not", "object"])

    assert response.status_code == 422
    assert upstream.calls == []


def test_stream_true_returns_400_without_calling_upstream_or_storing_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPSCANVAS_API_OPENAI_PROXY_ENABLED", "true")
    monkeypatch.setenv("OPSCANVAS_API_OPENAI_UPSTREAM_API_KEY", "sk-upstream-secret")
    app = create_app()
    upstream = RecordingAsyncClient(httpx.Response(200, json={"id": "chatcmpl_unused"}))
    app.state.openai_proxy_http_client = upstream
    client = TestClient(app)

    response = client.post(
        "/v1/chat/completions",
        json={"model": "gpt-5.4-mini", "stream": True},
    )

    assert response.status_code == 400
    assert "streaming is not supported" in response.json()["detail"].lower()
    assert upstream.calls == []
    assert client.get("/v1/runs").json() == []


def test_successful_upstream_response_is_returned_and_canonical_run_is_queryable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPSCANVAS_API_OPENAI_PROXY_ENABLED", "true")
    monkeypatch.setenv("OPSCANVAS_API_OPENAI_UPSTREAM_API_KEY", "sk-upstream-secret")
    app = create_app()
    upstream_body = {
        "id": "chatcmpl_123",
        "object": "chat.completion",
        "model": "gpt-5.4-mini",
        "choices": [
            {"index": 0, "finish_reason": "stop", "message": {"content": "raw completion secret"}}
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }
    upstream = RecordingAsyncClient(
        httpx.Response(
            200,
            json=upstream_body,
            headers={
                "Content-Type": "application/json",
                "X-Request-ID": "req_upstream",
                "X-RateLimit-Limit-Requests": "500",
                "Set-Cookie": "session=secret",
                "Authorization": "Bearer should-not-return",
            },
        )
    )
    app.state.openai_proxy_http_client = upstream
    client = TestClient(app)

    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-5.4-mini",
            "messages": [{"role": "user", "content": "raw prompt secret"}],
        },
        headers={
            "Authorization": "Bearer opscanvas-caller-key",
            "OpenAI-Organization": "org_safe",
            "Cookie": "session=caller-secret",
        },
    )

    assert response.status_code == 200
    assert response.json() == upstream_body
    assert response.headers["content-type"] == "application/json"
    assert response.headers["x-request-id"] == "req_upstream"
    assert response.headers["x-ratelimit-limit-requests"] == "500"
    assert "set-cookie" not in response.headers
    assert response.headers.get("authorization") is None

    assert len(upstream.calls) == 1
    upstream_call = upstream.calls[0]
    assert upstream_call["url"] == "http://testserver/v1/chat/completions"
    upstream_headers = upstream_call["headers"]
    assert isinstance(upstream_headers, dict)
    assert upstream_headers["Authorization"] == "Bearer sk-upstream-secret"
    assert upstream_headers["openai-organization"] == "org_safe"
    assert "opscanvas-caller-key" not in json.dumps(upstream_headers)
    assert "caller-secret" not in json.dumps(upstream_headers)

    runs_response = client.get("/v1/runs")
    assert runs_response.status_code == 200
    runs = runs_response.json()
    assert len(runs) == 1
    assert runs[0]["status"] == "succeeded"
    assert runs[0]["runtime"] == "openai-compatible-proxy"
    assert runs[0]["total_tokens"] == 15
    assert runs[0]["cost_usd"] is not None

    run_id = runs[0]["id"]
    run = client.get(f"/v1/runs/{run_id}").json()
    spans = client.get(f"/v1/runs/{run_id}/spans").json()
    assert run["metadata"]["provider"] == "openai"
    assert run["metadata"]["model"] == "gpt-5.4-mini"
    assert run["metadata"]["proxy.upstream_status_code"] == 200
    assert len(spans) == 1
    assert spans[0]["kind"] == "model_call"
    assert spans[0]["usage"]["input_tokens"] == 10
    assert spans[0]["usage"]["output_tokens"] == 5
    assert spans[0]["usage"]["total_tokens"] == 15

    serialized_run = json.dumps(run)
    for secret in [
        "raw prompt secret",
        "raw completion secret",
        "opscanvas-caller-key",
        "sk-upstream-secret",
        "caller-secret",
    ]:
        assert secret not in serialized_run


def test_upstream_non_2xx_response_is_returned_and_failed_run_is_stored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPSCANVAS_API_OPENAI_PROXY_ENABLED", "true")
    monkeypatch.setenv("OPSCANVAS_API_OPENAI_UPSTREAM_API_KEY", "sk-upstream-secret")
    app = create_app()
    upstream = RecordingAsyncClient(
        httpx.Response(
            429,
            json={"error": {"message": "provider rate limited raw text"}},
            headers={"Content-Type": "application/json", "X-Request-ID": "req_rate_limited"},
        )
    )
    app.state.openai_proxy_http_client = upstream
    client = TestClient(app)

    response = client.post(
        "/v1/chat/completions",
        json={"model": "gpt-5.4-mini", "messages": [{"role": "user", "content": "raw prompt"}]},
    )

    assert response.status_code == 429
    assert response.json() == {"error": {"message": "provider rate limited raw text"}}

    runs = client.get("/v1/runs").json()
    assert len(runs) == 1
    assert runs[0]["status"] == "failed"
    run = client.get(f"/v1/runs/{runs[0]['id']}").json()
    assert run["spans"][0]["attributes"]["http.status_code"] == 429


def test_transport_error_returns_502_and_stores_failed_run_without_secret_leakage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPSCANVAS_API_OPENAI_PROXY_ENABLED", "true")
    monkeypatch.setenv("OPSCANVAS_API_OPENAI_UPSTREAM_API_KEY", "sk-upstream-secret")
    app = create_app()
    upstream = RecordingAsyncClient(exc=httpx.ConnectError("connect failed sk-upstream-secret"))
    app.state.openai_proxy_http_client = upstream
    client = TestClient(app)

    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-5.4-mini",
            "messages": [{"role": "user", "content": "raw prompt secret"}],
        },
        headers={"Authorization": "Bearer opscanvas-caller-key"},
    )

    assert response.status_code == 502
    assert response.json() == {"detail": "OpenAI upstream request failed."}
    runs = client.get("/v1/runs").json()
    assert len(runs) == 1
    assert runs[0]["status"] == "failed"
    run = client.get(f"/v1/runs/{runs[0]['id']}").json()
    assert run["metadata"]["proxy.upstream_status_code"] == 502

    serialized = json.dumps(run)
    for secret in ["raw prompt secret", "sk-upstream-secret", "opscanvas-caller-key"]:
        assert secret not in serialized
