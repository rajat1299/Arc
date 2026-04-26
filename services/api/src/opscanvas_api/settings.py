from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for the OpsCanvas API service."""

    service_name: str = "opscanvas-api"
    version: str = "0.1.0"

    model_config = SettingsConfigDict(env_prefix="OPSCANVAS_API_")


def get_settings() -> Settings:
    return Settings()
