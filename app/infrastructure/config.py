"""Central application configuration.

Loads and validates settings from environment variables (and an optional
`.env` file) so that missing or malformed configuration fails fast at
startup rather than causing obscure errors deeper in the application.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration sourced from the environment."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    openai_api_key: str | None = None
    database_url: str = "sqlite:///./database/currentmind.db"
    rss_url: str = "https://indianexpress.com/section/upsc-current-affairs/feed/"
    log_level: str = "INFO"
    llm_model: str | None = None


@lru_cache
def get_settings() -> Settings:
    """Return the cached, validated application settings."""
    return Settings()
