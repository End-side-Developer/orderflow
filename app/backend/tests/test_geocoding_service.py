from __future__ import annotations

from uuid import uuid4

from orderflow_api.api import geocoding_service
from orderflow_api.api.geocode_cache_persistence import GeocodeCacheEntry
from orderflow_api.api.geocoding_service import (
    build_extracted_places,
    geocode_place,
    normalize_place_name,
)
from orderflow_api.schemas.page_summaries import ExtractedPlace


def test_normalize_place_name_strips_punctuation_and_case() -> None:
    assert normalize_place_name("  Sector-14, Gurugram! ") == "sector 14 gurugram"


def test_dedupe_places_collapses_repeats() -> None:
    places = build_extracted_places(
        [
            {"name": "Delhi", "place_type": "jurisdiction"},
            {"name": "delhi", "place_type": "jurisdiction", "mention_count": 2},
            {"name": "DELHI", "place_type": "jurisdiction"},
        ],
        page_number=3,
    )

    assert len(places) == 1
    assert places[0].normalized_name == "delhi"
    assert places[0].mention_count == 4
    assert places[0].source_page_number == 3


def test_geocode_place_uses_cache(monkeypatch) -> None:  # noqa: ANN001
    place = _place("Delhi")
    cache_entry = GeocodeCacheEntry(
        normalized_name="delhi",
        state_hint="delhi",
        query="Delhi, India",
        lat=28.6139,
        lng=77.209,
        confidence=0.91,
        source="nominatim",
        provider_payload=None,
        negative_expires_at=None,
    )

    monkeypatch.setattr(
        geocoding_service.geocode_cache_persistence,
        "get_cached_geocode",
        lambda normalized_name, state_hint: cache_entry,
    )
    monkeypatch.setattr(
        geocoding_service,
        "_search_nominatim",
        lambda query: (_ for _ in ()).throw(AssertionError("should not call HTTP")),
    )

    geocoded = geocode_place(place, state_hint="Delhi")

    assert geocoded.lat == 28.6139
    assert geocoded.lng == 77.209
    assert geocoded.geocode_source == "cache"


def test_geocode_place_handles_failure(monkeypatch) -> None:  # noqa: ANN001
    place = _place("Asdfqwerville")
    writes: list[dict[str, object]] = []

    monkeypatch.setattr(
        geocoding_service.geocode_cache_persistence,
        "get_cached_geocode",
        lambda normalized_name, state_hint: None,
    )
    monkeypatch.setattr(geocoding_service, "_search_nominatim", lambda query: None)
    monkeypatch.setattr(
        geocoding_service.geocode_cache_persistence,
        "upsert_geocode_cache",
        lambda **kwargs: writes.append(kwargs),
    )

    geocoded = geocode_place(place)

    assert geocoded.lat is None
    assert geocoded.lng is None
    assert geocoded.geocode_source == "none"
    assert writes
    assert writes[0]["negative_expires_at"] is not None


def test_geocode_place_india_bias(monkeypatch) -> None:  # noqa: ANN001
    captured: dict[str, str] = {}

    class FakeResponse:
        def __enter__(self):  # noqa: ANN201
            return self

        def __exit__(self, *args):  # noqa: ANN002
            return False

        def read(self) -> bytes:
            return b'[{"lat":"28.6139","lon":"77.2090","importance":0.8}]'

    def fake_urlopen(request, timeout):  # noqa: ANN001
        captured["url"] = request.full_url
        captured["user_agent"] = request.headers["User-agent"]
        return FakeResponse()

    monkeypatch.setattr(geocoding_service.urllib_request, "urlopen", fake_urlopen)
    monkeypatch.setattr(geocoding_service.settings, "orderflow_api_geocoder_pace_seconds", 0)

    result = geocoding_service._search_nominatim("Delhi, India")

    assert result is not None
    assert "countrycodes=in" in captured["url"]
    assert captured["user_agent"]


def _place(name: str) -> ExtractedPlace:
    return ExtractedPlace(
        id=uuid4(),
        name=name,
        normalized_name=normalize_place_name(name),
        place_type="jurisdiction",
        state=None,
        district=None,
        raw_text_span=None,
        lat=None,
        lng=None,
        geocode_confidence=0.0,
        geocode_source="none",
        source_page_number=1,
        mention_count=1,
    )
