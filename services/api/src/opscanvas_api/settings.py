from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for the OpsCanvas API service."""

    service_name: str = "opscanvas-api"
    version: str = "0.1.0"
    store_backend: Literal["memory", "clickhouse"] = "memory"
    clickhouse_host: str = "127.0.0.1"
    clickhouse_port: int = 8123
    clickhouse_username: str = "opscanvas"
    clickhouse_password: str = "opscanvas_dev_password"
    clickhouse_database: str = "opscanvas"
    clickhouse_secure: bool = False

    model_config = SettingsConfigDict(env_prefix="OPSCANVAS_API_")


def get_settings() -> Settings:
    return Settings()
