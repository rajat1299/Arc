import importlib

from opscanvas_claude import OpsCanvasConfig


def test_config_defaults() -> None:
    config = OpsCanvasConfig.from_env({})

    assert config.endpoint is None
    assert config.api_key is None
    assert config.project_id is None
    assert config.environment == "development"
    assert config.timeout_seconds == 10.0


def test_config_loads_opscanvas_environment() -> None:
    config = OpsCanvasConfig.from_env(
        {
            "OPSCANVAS_ENDPOINT": "https://ingest.example.test",
            "OPSCANVAS_API_KEY": "key_123",
            "OPSCANVAS_PROJECT_ID": "project_123",
            "OPSCANVAS_ENVIRONMENT": "production",
            "OPSCANVAS_TIMEOUT_SECONDS": "2.5",
        }
    )

    assert config.endpoint == "https://ingest.example.test"
    assert config.api_key == "key_123"
    assert config.project_id == "project_123"
    assert config.environment == "production"
    assert config.timeout_seconds == 2.5


def test_empty_environment_values_are_treated_as_missing() -> None:
    config = OpsCanvasConfig.from_env(
        {
            "OPSCANVAS_ENDPOINT": "",
            "OPSCANVAS_API_KEY": "",
            "OPSCANVAS_PROJECT_ID": "",
            "OPSCANVAS_ENVIRONMENT": "",
        }
    )

    assert config.endpoint is None
    assert config.api_key is None
    assert config.project_id is None
    assert config.environment == "development"


def test_importing_package_without_claude_agent_sdk_works() -> None:
    package = importlib.import_module("opscanvas_claude")

    assert package.OpsCanvasConfig is OpsCanvasConfig
