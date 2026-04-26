from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Agent Workforce Orchestrator"
    environment: str = "development"
    postgres_dsn: str = "postgresql://agentos:agentos@localhost:5432/agentos"
    redis_url: str = "redis://localhost:6379/0"
    default_llm_provider: str = "local_echo"
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com"
    openai_timeout_seconds: int = 60

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
