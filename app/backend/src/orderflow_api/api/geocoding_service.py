from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
import re
import time
from typing import Any
from urllib import parse as urllib_parse
from urllib import request as urllib_request
from uuid import uuid4

from orderflow_api.api import geocode_cache_persistence
from orderflow_api.core.config import settings
from orderflow_api.schemas.page_summaries import ExtractedPlace, PlaceType


_PUNCTUATION_RE = re.compile(r"[^\w\s]", re.UNICODE)
_WHITESPACE_RE = re.compile(r"\s+")
_LOCAL_PLACE_FALLBACKS: dict[str, tuple[float, float, float]] = {
    "delhi": (28.6139, 77.2090, 0.72),
    "new delhi": (28.6139, 77.2090, 0.74),
    "mumbai": (19.0760, 72.8777, 0.72),
    "bengaluru": (12.9716, 77.5946, 0.72),
    "bangalore": (12.9716, 77.5946, 0.72),
    "chennai": (13.0827, 80.2707, 0.72),
    "kolkata": (22.5726, 88.3639, 0.72),
    "hyderabad": (17.3850, 78.4867, 0.72),
    "pune": (18.5204, 73.8567, 0.72),
    "ahmedabad": (23.0225, 72.5714, 0.72),
    "jaipur": (26.9124, 75.7873, 0.72),
    "lucknow": (26.8467, 80.9462, 0.72),
    "patna": (25.5941, 85.1376, 0.72),
    "bhopal": (23.2599, 77.4126, 0.72),
    "indore": (22.7196, 75.8577, 0.72),
    "gurugram": (28.4595, 77.0266, 0.72),
    "gurgaon": (28.4595, 77.0266, 0.72),
    "noida": (28.5355, 77.3910, 0.72),
    "chandigarh": (30.7333, 76.7794, 0.72),
}


def normalize_place_name(value: str) -> str:
    """Normalize place mentions for intra-page dedupe and geocode caching."""
    cleaned = _PUNCTUATION_RE.sub(" ", value.lower())
    return _WHITESPACE_RE.sub(" ", cleaned).strip()


def build_extracted_places(
    candidates: list[dict[str, Any]],
    *,
    page_number: int,
) -> list[ExtractedPlace]:
    """Create typed, intra-page deduplicated place records from raw candidates."""
    grouped: dict[str, dict[str, Any]] = {}

    for candidate in candidates:
        raw_name = str(candidate.get("name") or "").strip()
        if not raw_name:
            continue

        normalized = normalize_place_name(raw_name)
        if not normalized:
            continue

        existing = grouped.get(normalized)
        mention_count = _coerce_positive_int(candidate.get("mention_count"), default=1)
        if existing is not None:
            existing["mention_count"] += mention_count
            continue

        grouped[normalized] = {
            "id": uuid4(),
            "name": raw_name,
            "normalized_name": normalized,
            "place_type": _coerce_place_type(candidate.get("place_type")),
            "state": _clean_optional_string(candidate.get("state")),
            "district": _clean_optional_string(candidate.get("district")),
            "raw_text_span": _clean_optional_string(candidate.get("raw_text_span")),
            "lat": None,
            "lng": None,
            "geocode_confidence": 0.0,
            "geocode_source": "none",
            "source_page_number": page_number,
            "mention_count": mention_count,
        }

    return [ExtractedPlace(**value) for value in grouped.values()]


def geocode_places(
    places: list[ExtractedPlace],
    *,
    state_hint: str | None = None,
    court_fallback_query: str | None = None,
) -> list[ExtractedPlace]:
    return [
        geocode_place(
            place,
            state_hint=state_hint,
            court_fallback_query=court_fallback_query,
        )
        for place in places
    ]


def geocode_place(
    place: ExtractedPlace,
    *,
    state_hint: str | None = None,
    court_fallback_query: str | None = None,
) -> ExtractedPlace:
    """Geocode a single place, preserving null coordinates on failure."""
    resolved_state_hint = place.state or state_hint
    local_fallback = _local_place_fallback(place)
    cached = geocode_cache_persistence.get_cached_geocode(
        place.normalized_name,
        resolved_state_hint,
    )
    if cached is not None:
        if not cached.is_positive and local_fallback is not None:
            return _apply_local_fallback(
                place,
                state_hint=resolved_state_hint,
                query=_build_query(place, state_hint=state_hint),
                fallback=local_fallback,
            )
        return place.model_copy(
            update={
                "lat": cached.lat,
                "lng": cached.lng,
                "geocode_confidence": cached.confidence,
                "geocode_source": "cache" if cached.is_positive else "none",
            }
        )

    query = _build_query(place, state_hint=state_hint)
    result = _search_nominatim(query)
    source = "nominatim"

    if result is None and place.place_type == "court" and court_fallback_query:
        query = court_fallback_query
        result = _search_nominatim(query)
        source = "fallback_court_metadata"

    if result is None and local_fallback is not None:
        return _apply_local_fallback(
            place,
            state_hint=resolved_state_hint,
            query=query,
            fallback=local_fallback,
        )

    if result is None:
        geocode_cache_persistence.upsert_geocode_cache(
            normalized_name=place.normalized_name,
            state_hint=resolved_state_hint,
            query=query,
            lat=None,
            lng=None,
            confidence=0.0,
            source="none",
            provider_payload=None,
            negative_expires_at=datetime.now(UTC) + timedelta(days=30),
        )
        return place.model_copy(
            update={
                "lat": None,
                "lng": None,
                "geocode_confidence": 0.0,
                "geocode_source": "none",
            }
        )

    lat = _coerce_float(result.get("lat"))
    lng = _coerce_float(result.get("lon"))
    confidence = _coerce_confidence(result.get("importance"))

    geocode_cache_persistence.upsert_geocode_cache(
        normalized_name=place.normalized_name,
        state_hint=resolved_state_hint,
        query=query,
        lat=lat,
        lng=lng,
        confidence=confidence,
        source=source,
        provider_payload=result,
        negative_expires_at=None,
    )
    return place.model_copy(
        update={
            "lat": lat,
            "lng": lng,
            "geocode_confidence": confidence,
            "geocode_source": source,
        }
    )


def _local_place_fallback(place: ExtractedPlace) -> tuple[float, float, float] | None:
    keys = [
        place.normalized_name,
        normalize_place_name(place.name),
        normalize_place_name(place.district or ""),
    ]
    for key in keys:
        if key in _LOCAL_PLACE_FALLBACKS:
            return _LOCAL_PLACE_FALLBACKS[key]
    return None


def _apply_local_fallback(
    place: ExtractedPlace,
    *,
    state_hint: str | None,
    query: str,
    fallback: tuple[float, float, float],
) -> ExtractedPlace:
    lat, lng, confidence = fallback
    geocode_cache_persistence.upsert_geocode_cache(
        normalized_name=place.normalized_name,
        state_hint=state_hint,
        query=query,
        lat=lat,
        lng=lng,
        confidence=confidence,
        source="local_fallback",
        provider_payload={"source": "local_city_centroid"},
        negative_expires_at=None,
    )
    return place.model_copy(
        update={
            "lat": lat,
            "lng": lng,
            "geocode_confidence": confidence,
            "geocode_source": "local_fallback",
        }
    )


def _search_nominatim(query: str) -> dict[str, Any] | None:
    params = {
        "format": "jsonv2",
        "q": query,
        "countrycodes": "in",
        "limit": "1",
        "addressdetails": "1",
    }
    url = "https://nominatim.openstreetmap.org/search?" + urllib_parse.urlencode(params)
    request = urllib_request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": settings.orderflow_api_geocoder_user_agent,
        },
        method="GET",
    )

    try:
        with urllib_request.urlopen(
            request,
            timeout=settings.orderflow_api_geocoder_timeout_seconds,
        ) as response:
            payload = response.read().decode("utf-8", errors="replace")
        if settings.orderflow_api_geocoder_pace_seconds > 0:
            time.sleep(settings.orderflow_api_geocoder_pace_seconds)
        parsed = json.loads(payload)
    except Exception:
        return None

    if not isinstance(parsed, list) or not parsed:
        return None
    first = parsed[0]
    return first if isinstance(first, dict) else None


def _build_query(place: ExtractedPlace, *, state_hint: str | None) -> str:
    parts = [place.name, place.district, place.state or state_hint, "India"]
    return ", ".join(part.strip() for part in parts if isinstance(part, str) and part.strip())


def _coerce_place_type(value: object) -> PlaceType:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"court", "property", "incident", "address", "jurisdiction", "other"}:
            return normalized  # type: ignore[return-value]
    return "other"


def _clean_optional_string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _coerce_positive_int(value: object, *, default: int) -> int:
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return max(number, 1)


def _coerce_float(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _coerce_confidence(value: object) -> float:
    number = _coerce_float(value)
    if number is None:
        return 0.75
    return min(max(number, 0.0), 1.0)
