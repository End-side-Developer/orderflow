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
    orderflow_log_level: str = Field(
        default="info", validation_alias="ORDERFLOW_LOG_LEVEL"
    )
    orderflow_ai_default_llm_provider: str = Field(
        default="openai",
        validation_alias="ORDERFLOW_AI_DEFAULT_LLM_PROVIDER",
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
    orderflow_ai_timeout_seconds: int = Field(
        default=45,
        validation_alias="ORDERFLOW_AI_TIMEOUT_SECONDS",
    )
    orderflow_ai_gemini_rate_limit_enabled: bool = Field(
        default=True,
        validation_alias="ORDERFLOW_AI_GEMINI_RATE_LIMIT_ENABLED",
    )
    orderflow_ai_gemini_requests_per_minute: int = Field(
        default=15,
        validation_alias="ORDERFLOW_AI_GEMINI_REQUESTS_PER_MINUTE",
    )
    orderflow_ai_gemini_tokens_per_minute: int = Field(
        default=1_000_000,
        validation_alias="ORDERFLOW_AI_GEMINI_TOKENS_PER_MINUTE",
    )
    orderflow_ai_gemini_requests_per_day: int = Field(
        default=1_500,
        validation_alias="ORDERFLOW_AI_GEMINI_REQUESTS_PER_DAY",
    )
    orderflow_ai_gemini_tokens_per_day: int = Field(
        default=1_000_000,
        validation_alias="ORDERFLOW_AI_GEMINI_TOKENS_PER_DAY",
    )
    orderflow_ai_gemini_max_wait_seconds: int = Field(
        default=90,
        validation_alias="ORDERFLOW_AI_GEMINI_MAX_WAIT_SECONDS",
    )
    orderflow_ai_gemini_chars_per_token: int = Field(
        default=4,
        validation_alias="ORDERFLOW_AI_GEMINI_CHARS_PER_TOKEN",
    )
    orderflow_ai_gemini_max_output_tokens: int = Field(
        default=1600,
        validation_alias="ORDERFLOW_AI_GEMINI_MAX_OUTPUT_TOKENS",
    )
    orderflow_ai_gemini_page_extraction_prompt_chars: int = Field(
        default=6000,
        validation_alias="ORDERFLOW_AI_GEMINI_PAGE_EXTRACTION_PROMPT_CHARS",
    )
    orderflow_ai_confidence_threshold: float = Field(
        default=0.78,
        validation_alias="ORDERFLOW_AI_CONFIDENCE_THRESHOLD",
    )
    orderflow_ai_prompt_version: str = Field(
        default="v1",
        validation_alias="ORDERFLOW_AI_PROMPT_VERSION",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
