from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for the OpsCanvas API service."""

    service_name: str = "opscanvas-api"
    version: str = "0.1.0"
    auth_enabled: bool = False
    api_keys: str = Field(default="", repr=False)
    store_backend: Literal["memory", "clickhouse"] = "memory"
    clickhouse_host: str = "127.0.0.1"
    clickhouse_port: int = 8123
    clickhouse_username: str = "opscanvas"
    clickhouse_password: str = "opscanvas_dev_password"
    clickhouse_database: str = "opscanvas"
    clickhouse_secure: bool = False
    openai_proxy_enabled: bool = False
    openai_upstream_base_url: str = "https://api.openai.com/v1"
    openai_upstream_api_key: str = Field(default="", repr=False)
    openai_proxy_timeout_seconds: float = 120.0
    proxy_capture_body: Literal["none", "summary", "redacted"] = "summary"

    model_config = SettingsConfigDict(env_prefix="OPSCANVAS_API_")


def get_settings() -> Settings:
    return Settings()
