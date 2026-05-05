from __future__ import annotations

from uuid import uuid4

from orderflow_api.api import map_renderer
from orderflow_api.schemas.page_summaries import ExtractedPlace


def test_render_static_map_returns_empty_bytes_without_pinnable_places() -> None:
    place = _place(lat=None, lng=None)

    assert map_renderer.render_static_map([place]) == b""


def test_render_static_map_draws_markers_and_flow_line(monkeypatch) -> None:  # noqa: ANN001
    captured = {"markers": 0, "lines": 0}

    class FakeImage:
        def save(self, buffer, format):  # noqa: ANN001, A002
            assert format == "PNG"
            buffer.write(b"fake-png")

    class FakeStaticMap:
        def __init__(self, width, height):  # noqa: ANN001
            assert width == 900
            assert height == 420

        def add_marker(self, marker):  # noqa: ANN001
            captured["markers"] += 1

        def add_line(self, line):  # noqa: ANN001
            captured["lines"] += 1

        def render(self):
            return FakeImage()

    monkeypatch.setattr(map_renderer, "StaticMap", FakeStaticMap)
    monkeypatch.setattr(map_renderer, "CircleMarker", lambda *args, **kwargs: ("marker", args))
    monkeypatch.setattr(map_renderer, "Line", lambda *args, **kwargs: ("line", args))

    payload = map_renderer.render_static_map(
        [_place(page_number=2), _place(page_number=1, name="Delhi High Court")]
    )

    assert payload == b"fake-png"
    assert captured["markers"] == 2
    assert captured["lines"] == 1


def _place(
    *,
    name: str = "Mumbai",
    page_number: int = 1,
    lat: float | None = 19.076,
    lng: float | None = 72.8777,
) -> ExtractedPlace:
    return ExtractedPlace(
        id=uuid4(),
        name=name,
        normalized_name=name.lower(),
        place_type="court",
        state="Maharashtra",
        district="Mumbai",
        raw_text_span="heard at Mumbai",
        lat=lat,
        lng=lng,
        geocode_confidence=0.9,
        geocode_source="nominatim",
        source_page_number=page_number,
        mention_count=1,
    )
