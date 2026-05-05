from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    orderflow_env: str = Field(default="local", validation_alias="ORDERFLOW_ENV")
    orderflow_log_level: str = Field(default="info", validation_alias="ORDERFLOW_LOG_LEVEL")
    orderflow_worker_task_queue: str = Field(
        default="orderflow-default",
        validation_alias="ORDERFLOW_WORKER_TASK_QUEUE",
    )
    orderflow_worker_temporal_host: str = Field(
        default="localhost:7233",
        validation_alias="ORDERFLOW_WORKER_TEMPORAL_HOST",
    )
    orderflow_worker_temporal_namespace: str = Field(
        default="default",
        validation_alias="ORDERFLOW_WORKER_TEMPORAL_NAMESPACE",
    )
    orderflow_intake_min_concurrency: int = Field(
        default=1,
        validation_alias="ORDERFLOW_INTAKE_MIN_CONCURRENCY",
        ge=1,
    )
    orderflow_intake_max_concurrency: int = Field(
        default=4,
        validation_alias="ORDERFLOW_INTAKE_MAX_CONCURRENCY",
        ge=1,
    )
    orderflow_ai_default_provider: str = Field(
        default="gemini",
        validation_alias="ORDERFLOW_AI_DEFAULT_PROVIDER",
    )
    orderflow_ai_default_model: str = Field(
        default="gemini-2.0-flash",
        validation_alias="ORDERFLOW_AI_DEFAULT_MODEL",
    )
    orderflow_ai_gemini_api_key: str | None = Field(
        default=None,
        validation_alias="ORDERFLOW_AI_GEMINI_API_KEY",
    )
    orderflow_ai_groq_api_key: str | None = Field(
        default=None,
        validation_alias="ORDERFLOW_AI_GROQ_API_KEY",
    )
    orderflow_ai_openai_api_key: str | None = Field(
        default=None,
        validation_alias="ORDERFLOW_AI_OPENAI_API_KEY",
    )
    orderflow_ai_anthropic_api_key: str | None = Field(
        default=None,
        validation_alias="ORDERFLOW_AI_ANTHROPIC_API_KEY",
    )
    orderflow_ai_timeout_seconds: int = Field(
        default=45,
        validation_alias="ORDERFLOW_AI_TIMEOUT_SECONDS",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
