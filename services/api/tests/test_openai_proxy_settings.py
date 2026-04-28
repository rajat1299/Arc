from opscanvas_api.settings import Settings


def test_openai_proxy_settings_are_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("OPSCANVAS_API_OPENAI_PROXY_ENABLED", raising=False)
    monkeypatch.delenv("OPSCANVAS_API_OPENAI_UPSTREAM_BASE_URL", raising=False)
    monkeypatch.delenv("OPSCANVAS_API_OPENAI_UPSTREAM_API_KEY", raising=False)
    monkeypatch.delenv("OPSCANVAS_API_OPENAI_PROXY_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("OPSCANVAS_API_PROXY_CAPTURE_BODY", raising=False)

    settings = Settings()

    assert settings.openai_proxy_enabled is False
    assert settings.openai_upstream_base_url == "https://api.openai.com/v1"
    assert settings.openai_upstream_api_key == ""
    assert settings.openai_proxy_timeout_seconds == 120.0
    assert settings.proxy_capture_body == "summary"


def test_openai_proxy_settings_load_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("OPSCANVAS_API_OPENAI_PROXY_ENABLED", "true")
    monkeypatch.setenv("OPSCANVAS_API_OPENAI_UPSTREAM_BASE_URL", "https://gateway.example/v1")
    monkeypatch.setenv("OPSCANVAS_API_OPENAI_UPSTREAM_API_KEY", "sk-secret")
    monkeypatch.setenv("OPSCANVAS_API_OPENAI_PROXY_TIMEOUT_SECONDS", "30.5")
    monkeypatch.setenv("OPSCANVAS_API_PROXY_CAPTURE_BODY", "redacted")

    settings = Settings()

    assert settings.openai_proxy_enabled is True
    assert settings.openai_upstream_base_url == "https://gateway.example/v1"
    assert settings.openai_upstream_api_key == "sk-secret"
    assert settings.openai_proxy_timeout_seconds == 30.5
    assert settings.proxy_capture_body == "redacted"
    assert "sk-secret" not in repr(settings)
