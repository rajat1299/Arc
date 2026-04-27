import pytest
from factories import canonical_run_payload
from fastapi.testclient import TestClient
from opscanvas_api.app import create_app

AUTH_HEADERS = {"Authorization": "Bearer alpha"}


@pytest.fixture(autouse=True)
def use_memory_store_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPSCANVAS_API_STORE_BACKEND", raising=False)


@pytest.fixture
def auth_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPSCANVAS_API_AUTH_ENABLED", "true")
    monkeypatch.setenv("OPSCANVAS_API_API_KEYS", "alpha")


def test_ingest_rejects_missing_bearer_credentials_when_auth_enabled(auth_enabled: None) -> None:
    client = TestClient(create_app())

    response = client.post("/v1/ingest/runs", json=canonical_run_payload())

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_ingest_rejects_invalid_bearer_credentials_when_auth_enabled(auth_enabled: None) -> None:
    client = TestClient(create_app())

    response = client.post(
        "/v1/ingest/runs",
        json=canonical_run_payload(),
        headers={"Authorization": "Bearer wrong"},
    )

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_ingest_accepts_configured_bearer_key_when_auth_enabled(auth_enabled: None) -> None:
    client = TestClient(create_app())

    response = client.post("/v1/ingest/runs", json=canonical_run_payload(), headers=AUTH_HEADERS)

    assert response.status_code == 202


def test_malformed_ingest_json_without_credentials_returns_401_before_body_parse(
    auth_enabled: None,
) -> None:
    client = TestClient(create_app())

    response = client.post(
        "/v1/ingest/runs",
        content="{",
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_malformed_ingest_json_with_invalid_credentials_returns_401_before_body_parse(
    auth_enabled: None,
) -> None:
    client = TestClient(create_app())

    response = client.post(
        "/v1/ingest/runs",
        content="{",
        headers={"Content-Type": "application/json", "Authorization": "Bearer wrong"},
    )

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_malformed_ingest_json_with_valid_credentials_returns_422(auth_enabled: None) -> None:
    client = TestClient(create_app())

    response = client.post(
        "/v1/ingest/runs",
        content="{",
        headers={"Content-Type": "application/json", **AUTH_HEADERS},
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/v1/runs"),
        ("get", "/v1/runs/run_123"),
        ("get", "/v1/runs/run_123/spans"),
        ("get", "/v1/runs/metrics"),
    ],
)
def test_run_routes_reject_missing_bearer_credentials_when_auth_enabled(
    auth_enabled: None,
    method: str,
    path: str,
) -> None:
    client = TestClient(create_app())

    response = getattr(client, method)(path)

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_run_routes_accept_configured_bearer_key_when_auth_enabled(auth_enabled: None) -> None:
    client = TestClient(create_app())
    ingest_response = client.post(
        "/v1/ingest/runs",
        json=canonical_run_payload(),
        headers=AUTH_HEADERS,
    )
    assert ingest_response.status_code == 202

    responses = [
        client.get("/v1/runs", headers=AUTH_HEADERS),
        client.get("/v1/runs/run_123", headers=AUTH_HEADERS),
        client.get("/v1/runs/run_123/spans", headers=AUTH_HEADERS),
        client.get("/v1/runs/metrics", headers=AUTH_HEADERS),
    ]

    assert [response.status_code for response in responses] == [200, 200, 200, 200]


def test_healthz_stays_public_when_auth_enabled(auth_enabled: None) -> None:
    client = TestClient(create_app())

    response = client.get("/healthz")

    assert response.status_code == 200


def test_protected_routes_fail_closed_when_auth_enabled_without_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPSCANVAS_API_AUTH_ENABLED", "true")
    monkeypatch.setenv("OPSCANVAS_API_API_KEYS", " \n, ")
    client = TestClient(create_app())

    response = client.get("/v1/runs", headers=AUTH_HEADERS)

    assert response.status_code == 503
