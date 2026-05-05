from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import SQLAlchemyError

from orderflow_api.core.db import get_engine


GEOCODE_CACHE_TABLE = sa.Table(
    "geocode_cache",
    sa.MetaData(),
    sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
    sa.Column("normalized_name", sa.String(length=255), nullable=False),
    sa.Column("state_hint", sa.String(length=100), nullable=False),
    sa.Column("query", sa.Text(), nullable=False),
    sa.Column("lat", sa.Numeric(10, 7), nullable=True),
    sa.Column("lng", sa.Numeric(10, 7), nullable=True),
    sa.Column("confidence", sa.Numeric(5, 4), nullable=False),
    sa.Column("source", sa.String(length=50), nullable=False),
    sa.Column("provider_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column("negative_expires_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("hit_count", sa.Integer(), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=False),
)


@dataclass(frozen=True)
class GeocodeCacheEntry:
    normalized_name: str
    state_hint: str
    query: str
    lat: float | None
    lng: float | None
    confidence: float
    source: str
    provider_payload: dict[str, Any] | None
    negative_expires_at: datetime | None

    @property
    def is_positive(self) -> bool:
        return self.lat is not None and self.lng is not None


def get_cached_geocode(
    normalized_name: str,
    state_hint: str | None,
) -> GeocodeCacheEntry | None:
    state_key = _state_key(state_hint)
    statement = sa.select(GEOCODE_CACHE_TABLE).where(
        GEOCODE_CACHE_TABLE.c.normalized_name == normalized_name,
        GEOCODE_CACHE_TABLE.c.state_hint == state_key,
    )

    try:
        with get_engine().begin() as connection:
            row = connection.execute(statement).mappings().first()
            if row is None:
                return None

            entry = _entry_from_row(row)
            if (
                not entry.is_positive
                and entry.negative_expires_at is not None
                and entry.negative_expires_at <= datetime.now(UTC)
            ):
                return None

            connection.execute(
                sa.update(GEOCODE_CACHE_TABLE)
                .where(GEOCODE_CACHE_TABLE.c.normalized_name == normalized_name)
                .where(GEOCODE_CACHE_TABLE.c.state_hint == state_key)
                .values(
                    hit_count=GEOCODE_CACHE_TABLE.c.hit_count + 1,
                    last_used_at=datetime.now(UTC),
                )
            )
            return entry
    except SQLAlchemyError:
        return None


def upsert_geocode_cache(
    *,
    normalized_name: str,
    state_hint: str | None,
    query: str,
    lat: float | None,
    lng: float | None,
    confidence: float,
    source: str,
    provider_payload: dict[str, Any] | None = None,
    negative_expires_at: datetime | None = None,
) -> None:
    state_key = _state_key(state_hint)
    now = datetime.now(UTC)
    values = {
        "id": uuid4(),
        "normalized_name": normalized_name,
        "state_hint": state_key,
        "query": query,
        "lat": lat,
        "lng": lng,
        "confidence": confidence,
        "source": source,
        "provider_payload": provider_payload,
        "negative_expires_at": negative_expires_at,
        "hit_count": 0,
        "created_at": now,
        "last_used_at": now,
    }

    statement = postgresql.insert(GEOCODE_CACHE_TABLE).values(**values)
    statement = statement.on_conflict_do_update(
        index_elements=["normalized_name", "state_hint"],
        set_={
            "query": query,
            "lat": lat,
            "lng": lng,
            "confidence": confidence,
            "source": source,
            "provider_payload": provider_payload,
            "negative_expires_at": negative_expires_at,
            "last_used_at": now,
        },
    )

    try:
        with get_engine().begin() as connection:
            connection.execute(statement)
    except SQLAlchemyError:
        return


def _state_key(state_hint: str | None) -> str:
    return (state_hint or "").strip().lower()


def _entry_from_row(row: Any) -> GeocodeCacheEntry:
    return GeocodeCacheEntry(
        normalized_name=row["normalized_name"],
        state_hint=row["state_hint"],
        query=row["query"],
        lat=_to_float(row["lat"]),
        lng=_to_float(row["lng"]),
        confidence=_to_float(row["confidence"]) or 0.0,
        source=row["source"],
        provider_payload=row["provider_payload"],
        negative_expires_at=row["negative_expires_at"],
    )


def _to_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    return None
