from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.pool import QueuePool

from orderflow_api.core.config import settings

_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine

    if _engine is None:
        _engine = create_engine(
            settings.orderflow_api_database_url,
            future=True,
            pool_pre_ping=True,
            poolclass=QueuePool,
            pool_size=10,
            max_overflow=20,
            pool_recycle=3600,
        )
    return _engine
