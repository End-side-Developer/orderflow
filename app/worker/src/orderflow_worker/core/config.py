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


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
