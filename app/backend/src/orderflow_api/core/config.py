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

    app_name: str = "OrderFlow API"
    app_version: str = "0.1.0"

    orderflow_env: str = Field(default="local", validation_alias="ORDERFLOW_ENV")
    orderflow_log_level: str = Field(default="info", validation_alias="ORDERFLOW_LOG_LEVEL")
    orderflow_api_host: str = Field(default="0.0.0.0", validation_alias="ORDERFLOW_API_HOST")
    orderflow_api_port: int = Field(default=8000, validation_alias="ORDERFLOW_API_PORT")
    orderflow_api_database_url: str = Field(
        default="postgresql+psycopg://orderflow:orderflow@localhost:5432/orderflow",
        validation_alias="ORDERFLOW_API_DATABASE_URL",
    )
    orderflow_api_use_stub_repository: bool = Field(
        default=False,
        validation_alias="ORDERFLOW_API_USE_STUB_REPOSITORY",
    )
    orderflow_api_s3_endpoint: str = Field(
        default="http://localhost:9000",
        validation_alias="ORDERFLOW_API_S3_ENDPOINT",
    )
    orderflow_api_s3_access_key: str = Field(
        default="minioadmin",
        validation_alias="ORDERFLOW_API_S3_ACCESS_KEY",
    )
    orderflow_api_s3_secret_key: str = Field(
        default="minioadmin",
        validation_alias="ORDERFLOW_API_S3_SECRET_KEY",
    )
    orderflow_api_s3_bucket: str = Field(
        default="orderflow-documents",
        validation_alias="ORDERFLOW_API_S3_BUCKET",
    )
    # "minio" (default; uses S3_ENDPOINT/_ACCESS_KEY/_SECRET_KEY) or
    # "azure_blob" (uses ORDERFLOW_API_AZURE_STORAGE_CONNECTION_STRING).
    # Bucket/container name is shared via ORDERFLOW_API_S3_BUCKET.
    orderflow_api_storage_backend: str = Field(
        default="minio",
        validation_alias="ORDERFLOW_API_STORAGE_BACKEND",
    )
    orderflow_api_azure_storage_connection_string: str | None = Field(
        default=None,
        validation_alias="ORDERFLOW_API_AZURE_STORAGE_CONNECTION_STRING",
    )
    orderflow_api_temporal_host: str = Field(
        default="localhost:7233",
        validation_alias="ORDERFLOW_API_TEMPORAL_HOST",
    )
    orderflow_api_temporal_namespace: str = Field(
        default="default",
        validation_alias="ORDERFLOW_API_TEMPORAL_NAMESPACE",
    )
    orderflow_api_temporal_task_queue: str = Field(
        default="orderflow-default",
        validation_alias="ORDERFLOW_API_TEMPORAL_TASK_QUEUE",
    )
    orderflow_api_temporal_workflow_id_prefix: str = Field(
        default="orderflow-intake",
        validation_alias="ORDERFLOW_API_TEMPORAL_WORKFLOW_ID_PREFIX",
    )
    # When true, the orchestrator skips Temporal entirely and serves a
    # synthesized intake job that auto-advances through the wizard stages.
    # Useful when running the API on infrastructure (Azure App Service,
    # Vercel, etc.) where deploying Temporal + a worker is impractical.
    orderflow_temporal_disabled: bool = Field(
        default=False,
        validation_alias="ORDERFLOW_TEMPORAL_DISABLED",
    )
    orderflow_api_cors_origins: str = Field(
        default="http://localhost:3000",
        validation_alias="ORDERFLOW_API_CORS_ORIGINS",
    )
    orderflow_otel_endpoint: str | None = Field(
        default=None,
        validation_alias="ORDERFLOW_OTEL_ENDPOINT",
    )
    orderflow_ai_enabled_default: bool = Field(
        default=False,
        validation_alias="ORDERFLOW_AI_ENABLED_DEFAULT",
    )
    orderflow_ai_allow_user_override: bool = Field(
        default=True,
        validation_alias="ORDERFLOW_AI_ALLOW_USER_OVERRIDE",
    )
    orderflow_ai_default_provider: str = Field(
        default="gemini",
        validation_alias="ORDERFLOW_AI_DEFAULT_PROVIDER",
    )
    orderflow_ai_default_model: str = Field(
        default="gemini-2.0-flash",
        validation_alias="ORDERFLOW_AI_DEFAULT_MODEL",
    )
    orderflow_ai_openai_api_key: str | None = Field(
        default=None,
        validation_alias="ORDERFLOW_AI_OPENAI_API_KEY",
    )
    orderflow_ai_anthropic_api_key: str | None = Field(
        default=None,
        validation_alias="ORDERFLOW_AI_ANTHROPIC_API_KEY",
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
        default=2048,
        validation_alias="ORDERFLOW_AI_GEMINI_MAX_OUTPUT_TOKENS",
    )
    orderflow_ai_gemini_max_clauses: int = Field(
        default=24,
        validation_alias="ORDERFLOW_AI_GEMINI_MAX_CLAUSES",
    )
    orderflow_ai_gemini_max_chars_per_clause: int = Field(
        default=600,
        validation_alias="ORDERFLOW_AI_GEMINI_MAX_CHARS_PER_CLAUSE",
    )
    orderflow_ai_gemini_judgment_prompt_chars: int = Field(
        default=9000,
        validation_alias="ORDERFLOW_AI_GEMINI_JUDGMENT_PROMPT_CHARS",
    )
    orderflow_ai_gemini_page_insight_prompt_chars: int = Field(
        default=4000,
        validation_alias="ORDERFLOW_AI_GEMINI_PAGE_INSIGHT_PROMPT_CHARS",
    )
    orderflow_api_geocoder_user_agent: str = Field(
        default="OrderFlow local development contact@example.invalid",
        validation_alias="ORDERFLOW_API_GEOCODER_USER_AGENT",
    )
    orderflow_api_geocoder_timeout_seconds: int = Field(
        default=10,
        validation_alias="ORDERFLOW_API_GEOCODER_TIMEOUT_SECONDS",
    )
    orderflow_api_geocoder_pace_seconds: float = Field(
        default=1.05,
        validation_alias="ORDERFLOW_API_GEOCODER_PACE_SECONDS",
    )
    orderflow_ai_max_clauses: int = Field(
        default=120,
        validation_alias="ORDERFLOW_AI_MAX_CLAUSES",
    )
    orderflow_translation_service_url: str = Field(
        default="http://localhost:5000",
        validation_alias="ORDERFLOW_TRANSLATION_SERVICE_URL",
    )
    orderflow_translation_timeout_seconds: int = Field(
        default=30,
        validation_alias="ORDERFLOW_TRANSLATION_TIMEOUT_SECONDS",
    )
    orderflow_translation_api_key: str | None = Field(
        default=None,
        validation_alias="ORDERFLOW_TRANSLATION_API_KEY",
    )
    orderflow_ocr_enabled: bool = Field(
        default=True,
        validation_alias="ORDERFLOW_OCR_ENABLED",
    )
    orderflow_ocr_primary_engine: str = Field(
        default="paddleocr",
        validation_alias="ORDERFLOW_OCR_PRIMARY_ENGINE",
    )
    orderflow_ocr_fallback_engine: str = Field(
        default="tesseract",
        validation_alias="ORDERFLOW_OCR_FALLBACK_ENGINE",
    )
    orderflow_ocr_dpi: int = Field(default=300, validation_alias="ORDERFLOW_OCR_DPI")
    orderflow_ocr_min_chars: int = Field(
        default=120,
        validation_alias="ORDERFLOW_OCR_MIN_CHARS",
    )
    orderflow_ocr_min_confidence: float = Field(
        default=0.55,
        validation_alias="ORDERFLOW_OCR_MIN_CONFIDENCE",
    )
    orderflow_ocr_tesseract_cmd: str = Field(
        default="tesseract",
        validation_alias="ORDERFLOW_OCR_TESSERACT_CMD",
    )
    orderflow_translation_max_retries: int = Field(
        default=3,
        validation_alias="ORDERFLOW_TRANSLATION_MAX_RETRIES",
    )

    orderflow_auth_required: bool = Field(
        default=True,
        validation_alias="ORDERFLOW_AUTH_REQUIRED",
    )
    orderflow_jwt_secret: str = Field(
        default="dev-only-change-me-in-prod",
        validation_alias="ORDERFLOW_JWT_SECRET",
    )
    orderflow_jwt_alg: str = Field(
        default="HS256",
        validation_alias="ORDERFLOW_JWT_ALG",
    )
    orderflow_jwt_issuer: str = Field(
        default="orderflow-api",
        validation_alias="ORDERFLOW_JWT_ISSUER",
    )
    orderflow_access_ttl_seconds: int = Field(
        default=900,
        validation_alias="ORDERFLOW_ACCESS_TTL_SECONDS",
    )
    orderflow_refresh_ttl_seconds: int = Field(
        default=1_209_600,
        validation_alias="ORDERFLOW_REFRESH_TTL_SECONDS",
    )
    orderflow_refresh_cookie_name: str = Field(
        default="orderflow_refresh",
        validation_alias="ORDERFLOW_REFRESH_COOKIE_NAME",
    )
    orderflow_refresh_cookie_domain: str | None = Field(
        default=None,
        validation_alias="ORDERFLOW_REFRESH_COOKIE_DOMAIN",
    )
    orderflow_refresh_cookie_secure: bool = Field(
        default=False,
        validation_alias="ORDERFLOW_REFRESH_COOKIE_SECURE",
    )
    orderflow_refresh_cookie_samesite: str = Field(
        default="lax",
        validation_alias="ORDERFLOW_REFRESH_COOKIE_SAMESITE",
    )
    orderflow_refresh_cookie_path: str = Field(
        default="/",
        validation_alias="ORDERFLOW_REFRESH_COOKIE_PATH",
    )

    @property
    def cors_origins(self) -> list[str]:
        return [item.strip() for item in self.orderflow_api_cors_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
