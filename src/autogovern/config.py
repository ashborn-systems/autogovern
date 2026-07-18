"""Application configuration, loaded from environment variables.

Values are read from real environment variables first, then from a local
.env file. A missing required field raises an error at startup.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Model provider configuration for generation and verification passes."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="MODEL_PROVIDER_")

    api_base: str
    model: str
    api_key_env: str
    temperature: float = 0.0


settings = Settings()  # type: ignore[call-arg]
