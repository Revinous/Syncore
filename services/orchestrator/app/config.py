from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Agent Workforce Orchestrator"
    environment: str = "development"
    syncore_runtime_mode: Literal["docker", "native"] = "docker"
    syncore_db_backend: Literal["postgres", "sqlite"] = "postgres"
    postgres_dsn: str = "postgresql://agentos:agentos@localhost:5432/agentos"
    sqlite_db_path: str = ".syncore/syncore.db"
    redis_url: str = "redis://localhost:6379/0"
    redis_required: bool = True
    default_llm_provider: str = "local_echo"
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com"
    openai_timeout_seconds: int = 60
    anthropic_api_key: str | None = None
    anthropic_base_url: str = "https://api.anthropic.com"
    anthropic_api_version: str = "2023-06-01"
    gemini_api_key: str | None = None
    gemini_base_url: str = "https://generativelanguage.googleapis.com"
    provider_failover_enabled: bool = True
    provider_fallback_order: str = "openai,anthropic,gemini,local_echo"
    run_default_timeout_seconds: int = 90
    run_stale_timeout_seconds: int = 1800
    max_concurrent_runs_per_task: int = 1
    max_concurrent_runs_per_workspace: int = 4
    slo_max_http_error_rate: float = 0.02
    slo_max_http_p95_latency_ms: float = 1200.0
    slo_min_run_success_rate: float = 0.97
    slo_min_context_savings_pct: float = 5.0
    slo_max_context_layering_fallback_rate: float = 0.4
    context_layering_enabled: bool = False
    context_layering_dual_mode: bool = False
    context_layering_fallback_threshold_pct: float = 2.0
    context_layering_fallback_min_samples: int = 5
    autonomy_enabled: bool = False
    autonomy_poll_interval_seconds: float = 2.0
    queue_worker_enabled: bool = False
    queue_worker_poll_interval_seconds: float = 1.0
    autonomy_default_model: str = "local_echo"
    autonomy_max_retries: int = 2
    autonomy_retry_base_seconds: float = 2.0
    autonomy_max_cycles: int = 2
    autonomy_max_total_steps: int = 12
    autonomy_review_pass_keyword: str = "PASS"
    autonomy_plan_min_chars: int = 80
    autonomy_execute_min_chars: int = 120
    autonomy_review_min_chars: int = 80
    autonomy_workspace_execution_enabled: bool = True
    autonomy_workspace_execution_profile: str = "balanced"
    autonomy_workspace_auto_approve_low_risk: bool = True
    autonomy_workspace_max_steps: int = 4
    autonomy_execute_plan_enabled: bool = True
    autonomy_failure_taxonomy_v2: bool = True
    autonomy_low_info_stop_enabled: bool = True
    autonomy_low_info_threshold: int = 2
    autonomy_max_provider_switches: int = 2
    api_auth_enabled: bool = False
    api_auth_token: str | None = None
    rate_limit_enabled: bool = False
    rate_limit_window_seconds: int = 60
    rate_limit_max_requests: int = 120

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
