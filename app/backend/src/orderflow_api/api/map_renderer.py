from __future__ import annotations

from io import BytesIO
from typing import Iterable, Literal

from orderflow_api.schemas.page_summaries import ExtractedPlace, PlaceType

try:  # Optional Plan C PDF dependency.
    from staticmap import CircleMarker, Line, StaticMap
except Exception:  # pragma: no cover - exercised by dependency-free runtime paths.
    CircleMarker = None  # type: ignore[assignment]
    Line = None  # type: ignore[assignment]
    StaticMap = None  # type: ignore[assignment]


MapMode = Literal["flow", "single-page"]

PLACE_COLORS: dict[PlaceType, str] = {
    "court": "#2563eb",
    "property": "#16a34a",
    "incident": "#dc2626",
    "address": "#f59e0b",
    "jurisdiction": "#7c3aed",
    "other": "#64748b",
}


class MapRenderingUnavailable(RuntimeError):
    """Raised when optional static map dependencies are not installed."""


def render_static_map(
    places: Iterable[ExtractedPlace],
    *,
    mode: MapMode = "flow",
    current_page: int | None = None,
    width: int = 900,
    height: int = 420,
) -> bytes:
    """Render a static PNG map for the PDF export.

    Coordinates are kept in the API's lat/lng shape, then converted to the
    lon/lat tuples expected by staticmap at the final rendering boundary.
    """

    visible_places = _pinnable_places(places, mode=mode, current_page=current_page)
    if not visible_places:
        return b""

    if StaticMap is None or CircleMarker is None:
        raise MapRenderingUnavailable(
            "Install the backend PDF extras to render maps: staticmap and its image dependencies."
        )

    static_map = StaticMap(width, height)
    coordinates = [(place.lng, place.lat) for place in visible_places]

    if mode == "flow" and len(coordinates) > 1:
        if Line is None:
            raise MapRenderingUnavailable("staticmap Line support is unavailable.")
        static_map.add_line(Line(coordinates, "#0f766e", 3))

    for place in visible_places:
        static_map.add_marker(
            CircleMarker(
                (place.lng, place.lat),
                PLACE_COLORS.get(place.place_type, PLACE_COLORS["other"]),
                14,
            )
        )

    image = static_map.render()
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def render_summary_map(places: Iterable[ExtractedPlace]) -> bytes:
    return render_static_map(places, mode="flow")


def render_page_map(places: Iterable[ExtractedPlace], *, page_number: int) -> bytes:
    return render_static_map(places, mode="single-page", current_page=page_number)


def _pinnable_places(
    places: Iterable[ExtractedPlace],
    *,
    mode: MapMode,
    current_page: int | None,
) -> list[ExtractedPlace]:
    filtered = [
        place
        for place in places
        if place.lat is not None
        and place.lng is not None
        and (mode == "flow" or place.source_page_number == current_page)
    ]
    if mode == "flow":
        return sorted(filtered, key=lambda place: place.source_page_number)
    return filtered
