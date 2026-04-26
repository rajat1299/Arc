from fastapi.testclient import TestClient
from opscanvas_api.app import create_app


def test_health_returns_service_status() -> None:
    client = TestClient(create_app())

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "opscanvas-api",
        "version": "0.1.0",
    }
