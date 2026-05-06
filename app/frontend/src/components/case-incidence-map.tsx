"use client";

import { useEffect, useMemo } from "react";
import L from "leaflet";
import {
  MapContainer,
  Marker,
  Polyline,
  Popup,
  TileLayer,
  useMap,
} from "react-leaflet";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

export type PlaceType =
  | "court"
  | "property"
  | "incident"
  | "address"
  | "jurisdiction"
  | "other";

export type GeocodeSource = "nominatim" | "cache" | "fallback_court_metadata" | "none";

export type ExtractedPlace = {
  id: string;
  name: string;
  normalized_name: string;
  place_type: PlaceType;
  state: string | null;
  district: string | null;
  raw_text_span: string | null;
  lat: number | null;
  lng: number | null;
  geocode_confidence: number;
  geocode_source: GeocodeSource;
  source_page_number: number;
  mention_count: number;
};

type CaseIncidenceMapProps = {
  places: ExtractedPlace[];
  mode: "flow" | "single-page";
  currentPage?: number;
  onPlaceClick?: (pageNumber: number) => void;
};

type VisiblePlace = ExtractedPlace & {
  lat: number;
  lng: number;
  flowIndex: number;
};

const PLACE_STYLES: Record<PlaceType, { label: string; short: string }> = {
  court: { label: "Court", short: "C" },
  property: { label: "Property", short: "P" },
  incident: { label: "Incident", short: "I" },
  address: { label: "Address", short: "A" },
  jurisdiction: { label: "Jurisdiction", short: "J" },
  other: { label: "Other", short: "O" },
};

const DEFAULT_CENTER: [number, number] = [22.9734, 78.6569];

export function CaseIncidenceMap({
  places,
  mode,
  currentPage,
  onPlaceClick,
}: CaseIncidenceMapProps) {
  const visiblePlaces = useMemo(() => {
    const pinnable = places
      .filter((place): place is ExtractedPlace & { lat: number; lng: number } => {
        return typeof place.lat === "number" && typeof place.lng === "number";
      })
      .filter((place) => {
        return mode === "flow" || place.source_page_number === currentPage;
      })
      .sort((a, b) => a.source_page_number - b.source_page_number);

    return pinnable.map((place, index) => ({
      ...place,
      flowIndex: index + 1,
    }));
  }, [currentPage, mode, places]);

  if (visiblePlaces.length === 0) {
    return null;
  }

  const positions = visiblePlaces.map(
    (place) => [place.lat, place.lng] satisfies [number, number],
  );
  const center = positions[0] ?? DEFAULT_CENTER;
  const shouldDrawFlow = mode === "flow" && positions.length > 1;

  return (
    <div className="case-incidence-map-shell">
      <MapContainer
        center={center}
        zoom={positions.length === 1 ? 10 : 5}
        scrollWheelZoom={false}
        className="case-incidence-map"
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <FitBounds positions={positions} />
        {shouldDrawFlow ? (
          <Polyline
            positions={positions}
            pathOptions={{ color: "#14b8a6", dashArray: "8 10", weight: 3 }}
          />
        ) : null}
        {visiblePlaces.map((place) => (
          <Marker
            key={`${place.id}-${place.flowIndex}`}
            position={[place.lat, place.lng]}
            icon={markerIcon(place, mode)}
          >
            <Popup>
              <div className="flex min-w-48 flex-col gap-2">
                <div>
                  <p className="text-sm font-semibold text-foreground">{place.name}</p>
                  <p className="text-xs text-muted-foreground">
                    {[place.district, place.state].filter(Boolean).join(", ") || "Location"}
                  </p>
                </div>
                <div className="flex flex-wrap gap-1">
                  <Badge variant="secondary">{PLACE_STYLES[place.place_type].label}</Badge>
                  <Badge variant="outline">Page {place.source_page_number}</Badge>
                </div>
                {place.raw_text_span ? (
                  <p className="text-xs text-muted-foreground">{place.raw_text_span}</p>
                ) : null}
                {onPlaceClick ? (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => onPlaceClick(place.source_page_number)}
                  >
                    Jump to page
                  </Button>
                ) : null}
              </div>
            </Popup>
          </Marker>
        ))}
      </MapContainer>
      <MapLegend />
    </div>
  );
}

function FitBounds({ positions }: { positions: [number, number][] }) {
  const map = useMap();

  useEffect(() => {
    if (positions.length === 1) {
      map.setView(positions[0], 10, { animate: false });
      return;
    }
    if (positions.length > 1) {
      map.fitBounds(L.latLngBounds(positions), { padding: [28, 28], animate: false });
    }
  }, [map, positions]);

  return null;
}

function markerIcon(place: VisiblePlace, mode: "flow" | "single-page") {
  const style = PLACE_STYLES[place.place_type];
  const content = mode === "flow" ? String(place.flowIndex) : style.short;

  return L.divIcon({
    className: `case-incidence-marker case-incidence-marker-${place.place_type}`,
    html: `<div class="ci-pin" title="${style.label}"><span>${content}</span></div>`,
    iconSize: [30, 38],
    iconAnchor: [15, 38],
    popupAnchor: [0, -34],
  });
}

function MapLegend() {
  return (
    <div className="case-incidence-map-legend">
      {(Object.keys(PLACE_STYLES) as PlaceType[]).map((type) => (
        <span key={type} className={`case-incidence-legend-item ci-legend-${type}`}>
          <span aria-hidden="true" />
          {PLACE_STYLES[type].label}
        </span>
      ))}
    </div>
  );
}


