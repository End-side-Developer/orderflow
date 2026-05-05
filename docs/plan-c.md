# Case Incidence Map for OrderFlow

## Context

OrderFlow ingests legal judgment PDFs and produces per-page AI summaries plus extracted obligations. Today the user has no way to see *where* events in a case happened geographically — court venues, property addresses, incident sites, jurisdictions are scattered through the prose. This plan adds a map widget that pins the places mentioned in a document so the reader can:

- See the **document-wide flow** of locations on the summary page (page 1 → page 2 → … → last page, drawn as a connected polyline).
- See **only the current page's** locations while reading the PDF page-by-page.
- See nothing at all when no place is mentioned (graceful absence).

The AI must do the detection — places are not currently extracted from page text (only court metadata sits in `cis.state`/`cis.district`).

## Approach (one-line summary)

Extend the existing per-page Gemini summary call to also emit a typed `places[]` array, geocode each place via OpenStreetMap Nominatim with a Postgres cache, persist as a JSONB column on `page_summaries`, render in-app with `react-leaflet` (numbered markers + category icons in flow mode, single-page filtering in PDF view), and render a static-image map into a new server-generated PDF export using the Python `staticmap` library.

## Data Model

### New `ExtractedPlace` (in `schemas/page_summaries.py`)
```
id: UUID
name: str                           # raw mention
normalized_name: str                # lower-cased, punctuation-stripped (cache key)
place_type: "court"|"property"|"incident"|"address"|"jurisdiction"|"other"
state: str|None
district: str|None
raw_text_span: str|None             # ~120-char snippet for tooltip
lat: float|None                     # null = geocoding failed → not pinned
lng: float|None
geocode_confidence: float
geocode_source: "nominatim"|"cache"|"fallback_court_metadata"|"none"
source_page_number: int
mention_count: int                  # intra-page dedup count
```

`PageSummaryRecord` gains `extracted_places: list[ExtractedPlace] = []` (backwards compatible — old clients ignore it).

### Storage decision: JSONB column on existing `page_summaries`, NOT a new table
Places are 1-to-1 owned by a page summary — same convention already used by `important_highlights` / `key_points` / `context_links`. Cascade-delete is free via the existing FK. Cross-doc joins are not required.

### New `geocode_cache` table (shared across docs)
Keyed by `(normalized_name, state_hint)`. Positive hits cached forever; negative hits 30-day TTL. Tracks `hit_count` / `last_used_at` for future pruning.

### Migration (Alembic — project already uses it)
One new revision: `app/backend/alembic/versions/20260503_01_case_incidence_places.py`, `down_revision = "20260502_03"`. Adds the JSONB column + creates `geocode_cache`.

## Extraction (single LLM call, not a new graph node)

Place extraction extends the existing `PageSummaryExtractor._ai_extract_page` Gemini prompt rather than adding a separate LangGraph node. Why:
- Doubles round-trips otherwise; the existing rate-limit guard is already tight.
- Keeps "what was on page N" co-located in one row.
- Gemini handles place NER co-located with summary tasks well.

Prompt addition:
```
4. PLACES: Identify Indian places (cities, districts, courts, properties, incident
   sites, jurisdictions) that physically exist and could be plotted on a map.
   - Skip purely abstract references ("the petitioner's residence" with no town).
   - Prefer the most specific form ("Sector 14 Gurugram, Haryana" over "Haryana").
   - Tag each with type: court | property | incident | address | jurisdiction | other.
   - Same place mentioned multiple times → return ONCE with mention_count = N.
```

JSON schema gains a `places[]` array with `name, place_type, state, district, raw_text_span, mention_count`.

Intra-page dedup runs immediately after the LLM call by `normalized_name`; cross-page dedup is **intentionally NOT done** — we need page-ordered duplicates to draw the page→page polyline in flow mode.

## Geocoding

Service: **OpenStreetMap Nominatim** (free, no key, India-bias via `countrycodes=in` + viewbox). Required `User-Agent` header with contact info. 1 RPS pacing built into the call (`time.sleep(1.05)` after each network hit).

Pipeline placement: backend, after LLM extraction and dedup, before persistence. Failure mode: persist place with `lat=null, lng=null, geocode_source="none"` (still useful for a future list view; frontend filters before pinning). Fallback: for `place_type=="court"` with no Nominatim hit, retry using `cis.court_name + cis.district + cis.state` and tag `geocode_source="fallback_court_metadata"`.

New module: `app/backend/src/orderflow_api/api/geocoding_service.py`.
Cache helpers: `app/backend/src/orderflow_api/api/geocode_cache_persistence.py`.

## API Changes

- `GET /api/v1/summaries/{document_id}` — response gains `extracted_places[]` per page (backwards-compat optional field). **No new endpoint needed for the summary view** — the frontend aggregates `summaries.flatMap(s => s.extracted_places)` itself.
- New `POST /api/v1/summaries/{document_id}/places/refresh` — re-runs only the place-extraction + geocode step on existing summaries (cheap; lets users opt in to map without forcing full re-summarize). Gated by `Permission.EXTRACTION_RUN`.

## Frontend

### New deps (in `app/frontend/package.json`)
```
"react-leaflet": "^4.2.1",
"leaflet": "^1.9.4",
"@types/leaflet": "^1.9.12"
```

Tile source: default OSM (free, attribution rendered automatically).

### New component — `app/frontend/src/components/case-incidence-map.tsx`

Single reusable component. Props: `places: MapPlace[]`, `mode: "flow" | "single-page"`, `currentPage?: number`, `onPlaceClick?: (page) => void`.

Behaviour:
- Filters out `lat == null` rows.
- `single-page` mode: keeps only `source_page_number === currentPage`.
- `flow` mode: sorts by `source_page_number`, draws a dashed `Polyline` connecting markers.
- `<FitBounds>` helper auto-zooms to all visible points (handles 1-pin and many-pin cases).
- Marker popup: name, district/state, page number, raw snippet, "Jump to page" button.
- Returns `null` if zero pinnable places (graceful absence at component level).

### Numbered markers in flow mode (decision: user-confirmed)
In `mode === "flow"`, build a custom `L.DivIcon` per marker showing the marker's index in the page-ordered sequence:
```ts
const numberedIcon = (n: number, type: PlaceType) =>
  L.divIcon({
    className: "case-incidence-marker",
    html: `<div class="ci-pin ci-${type}"><span>${n}</span></div>`,
    iconSize: [28, 36],
    iconAnchor: [14, 36],
  });
```
The numbering order is `source_page_number` ascending, then mention order within page. CSS in a co-located stylesheet (`case-incidence-map.css`) adds the colored bubble/teardrop shape and a tail. In `single-page` mode, plain pins are used (numbering would be misleading because only one page is shown).

### Category icons (decision: user-confirmed)
Each `place_type` gets a distinct color + emoji glyph rendered inside the same `L.DivIcon`:
- `court` → blue, balance-scale glyph
- `property` → green, home glyph
- `incident` → red, alert glyph
- `address` → grey, mailbox glyph
- `jurisdiction` → purple, map glyph
- `other` → neutral, dot
Glyphs ship as inline SVG (no extra fetch). The `legend` block in the map Card explains the colors.

### SSR
Leaflet touches `window` → load via `dynamic(() => import(...), { ssr: false })`. Pattern already used by `PdfViewer` in this codebase.

### Render placement — Summary page (`app/frontend/src/app/document-summary/page.tsx`)
Inside `viewMode === "summary"` branch, after `<DocumentAdvocatesStrip>`, render a `Card` titled "Case incidence flow" with the map in `mode="flow"`. Skip the whole Card if `allPlaces.length === 0`. `onPlaceClick` jumps to the matching page within the same view.

### Render placement — PDF viewer (`app/frontend/src/components/pdf-viewer.tsx`)
Add a `places?: ExtractedPlace[]` prop. Below the canvas (near `RecommendedAdvocatesPanel`), render a collapsible `<details>` titled "Locations on this page" that wraps the map in `mode="single-page"` with `currentPage`. Drawer (not side panel) chosen to avoid stealing horizontal space from the PDF and existing overlays. Suppressed if no pinnable places exist for this page.

### TypeScript
Extend the local `PageSummary` interface in `document-summary/page.tsx` with `extracted_places: ExtractedPlace[]`. Re-export the type from `case-incidence-map.tsx` so PDF viewer can import it.

## PDF export (decision: user-confirmed — include map in downloadable PDF)

A new server-side PDF export is added so the case incidence map travels with the document handoff (court submissions, internal review packets).

### Library choice — `staticmap` (Python) for the map snapshot, `weasyprint` for PDF assembly

`staticmap` (PyPI: `staticmap==0.5.7`) draws OSM tiles + markers + polylines into a PNG entirely in Python. No headless browser, no Chromium, no Node. ~1 MB of tile cache per render. This is far simpler than Playwright/Puppeteer and matches the static, server-rendered nature of an export.

`weasyprint` (already a candidate Python PDF generator; not yet installed) renders an HTML+CSS template into PDF and natively embeds PNGs. Both go into `app/backend/pyproject.toml`.

### Pipeline

1. New module `app/backend/src/orderflow_api/api/map_renderer.py`:
   - `render_flow_map_png(places: list[ExtractedPlace]) -> bytes` — full-document flow map (numbered markers + dashed polyline through them).
   - `render_page_map_png(places: list[ExtractedPlace], page_number: int) -> bytes` — markers for a single page only.
   - Categories produce different marker colors via `staticmap.IconMarker` (one tiny PNG icon shipped per category in `app/backend/assets/map_icons/`).
   - Returns empty `bytes()` (sentinel) when no pinnable places — caller skips embedding.
2. New export endpoint `POST /api/v1/exports/case-bundle/pdf` in `app/backend/src/orderflow_api/api/routes/exports.py`:
   - Body: `{ document_id, include_per_page_maps: bool = true, include_summary_map: bool = true }`.
   - Loads page summaries (with `extracted_places`), renders flow + per-page maps, fills an HTML template, returns the PDF blob via `StreamingResponse`.
3. New Jinja2 template at `app/backend/src/orderflow_api/templates/case_bundle.html`:
   - Cover page: case metadata + flow map (full width).
   - Per-page section: page summary text + key points + per-page map (only if that page has pinnable places).
   - CSS print rules for page breaks between pages.

### Frontend wiring

Add an "Export PDF with map" button to the summary page header. Calls the new endpoint and triggers a browser download. Permission-gated (`Permission.EXPORT_RUN` if it exists; else `Permission.EXTRACTION_RUN`).

### Files added for PDF export
- `app/backend/src/orderflow_api/api/map_renderer.py`
- `app/backend/src/orderflow_api/templates/case_bundle.html`
- `app/backend/assets/map_icons/{court,property,incident,address,jurisdiction,other}.png`
- `app/backend/tests/test_map_renderer.py`
- `app/backend/tests/test_exports_case_bundle.py`

### Files modified for PDF export
- `app/backend/pyproject.toml` — add `staticmap`, `weasyprint`, `jinja2` (jinja2 may already be present transitively).
- `app/backend/src/orderflow_api/api/routes/exports.py` — add `case-bundle/pdf` route.
- `app/frontend/src/app/document-summary/page.tsx` — "Export PDF" button + download handler.
- `app/frontend/src/lib/api/client.ts` — `exportCaseBundlePdf(documentId)` helper.

### WeasyPrint system deps note
WeasyPrint needs Pango/Cairo/GDK-PixBuf system libraries. The Dockerfile (or whichever runtime config the team uses for backend deploys) needs `libpango-1.0-0 libpangoft2-1.0-0` etc. installed. Verify in `app/backend/Dockerfile` or `infra/` before merging.

## Backfill

Two paths, both ship together:

1. **"Regenerate map" button** in the new Card header → `POST /summaries/{id}/places/refresh`. Visible to users with extraction permission. Cheaper than full re-summary because it skips summary/key-points and re-runs only place extraction + geocode + UPDATE on the JSONB column.
2. **One-shot script** `app/backend/scripts/backfill_extracted_places.py` — pages through documents whose `page_summaries.extracted_places IS NULL` and refreshes them in batches. Run once after the migration deploys.

## Critical files

**To create**
- `app/backend/alembic/versions/20260503_01_case_incidence_places.py`
- `app/backend/src/orderflow_api/api/geocoding_service.py`
- `app/backend/src/orderflow_api/api/geocode_cache_persistence.py`
- `app/backend/scripts/backfill_extracted_places.py`
- `app/backend/tests/test_geocoding_service.py`
- `app/backend/tests/test_page_summary_engine_places.py`
- `app/frontend/src/components/case-incidence-map.tsx`

**To modify**
- `app/backend/src/orderflow_api/schemas/page_summaries.py` — add `ExtractedPlace`, extend `PageSummaryRecord`.
- `app/backend/src/orderflow_api/api/page_summary_engine.py` — extend Gemini prompt, dedupe, geocode.
- `app/backend/src/orderflow_api/api/page_summary_persistence.py` — add column to table def + CRUD plumbing.
- `app/backend/src/orderflow_api/api/routes/page_summaries.py` — add `places/refresh` route.
- `app/frontend/package.json` — add `react-leaflet`, `leaflet`, `@types/leaflet`.
- `app/frontend/src/app/document-summary/page.tsx` — extend `PageSummary` type, dynamic-import map, render Card in summary view, pass places to `<PdfViewer>`.
- `app/frontend/src/components/pdf-viewer.tsx` — accept `places` prop, render collapsible map below canvas.

**Reused (do NOT recreate)**
- `PageSummaryExtractor` in `page_summary_engine.py` — owns Gemini call.
- `_GeminiQuotaGuard` in `gemini_client.py` — already rate-limits Gemini.
- `dynamic()` SSR pattern — copied from existing `PdfViewer` import.
- `Card` / `CardHeader` / `CardContent` shadcn components — match summary page style.

## Verification

### Backend unit tests (`app/backend/tests/`)
- `test_geocoding_service.py`:
  - `test_normalize_place_name` — punctuation/case stripping.
  - `test_dedupe_places_collapses_repeats` — `[Delhi, delhi, DELHI]` → 1 row, mention_count=3.
  - `test_geocode_place_uses_cache` — pre-populated cache, asserts no HTTP call.
  - `test_geocode_place_handles_failure` — mocked 5xx → null-coord result + negative cache write.
  - `test_geocode_place_india_bias` — URL contains `countrycodes=in`.
- `test_page_summary_engine_places.py`:
  - `test_ai_extract_returns_places` — mocked Gemini → `extracted_places` populated.
  - `test_extraction_handles_missing_places_field` — old-shape Gemini → `[]`, no crash.
  - `test_geocoding_failure_persists_with_null_coords`.

### API integration
- `test_summaries_endpoint_includes_extracted_places`.
- `test_places_refresh_endpoint_updates_only_places_column`.

### End-to-end manual
1. Multi-place doc (5+ pages, multiple cities) → flow polyline visible in summary, PDF view filters to current page.
2. Zero-place doc → no map Card on either view (assert no DOM presence).
3. Single-place doc → one pin, no polyline.
4. Synthetic unfindable name ("Asdfqwerville") → API persists with `lat=null`, frontend skips it.
5. 20+ places → `fitBounds` works, no React lag.
6. Cache hit verification — second doc mentioning the same place geocodes near-instant (verify via logs).

### Run commands
```
# Backend
uv run pytest app/backend/tests/test_geocoding_service.py
uv run pytest app/backend/tests/test_page_summary_engine_places.py
uv run alembic upgrade head

# Frontend
pnpm --filter frontend install
pnpm --filter frontend dev   # then upload a multi-place doc and visually verify both views
```

## Alternatives considered (one-line each)

- **Mapbox vs Leaflet** → Leaflet (free, no token, sufficient for markers + polylines).
- **Google Geocoding vs Nominatim** → Nominatim (free, allows permanent caching; Google TOS forbids it).
- **Separate NER step vs extend existing prompt** → extend (avoids doubling Gemini round-trips).
- **Separate `page_places` table vs JSONB column** → JSONB (matches existing `key_points` convention; no cross-doc joins needed).
- **Side panel vs drawer in PDF view** → drawer (canvas already shares horizontal space with overlays).
- **Cross-page dedup vs keep page-ordered duplicates** → keep duplicates (flow polyline needs the temporal sequence).

## Decisions confirmed by user

1. **PDF export with map → IN SCOPE.** Server-rendered via `staticmap` + `weasyprint`. New endpoint `POST /api/v1/exports/case-bundle/pdf`.
2. **Numbered markers in flow mode → YES.** `L.DivIcon` with index labels in page-order sequence.
3. **Geocoder → Nominatim** (free, India-bias, with permanent positive cache + 30-day negative cache).
4. **Category icons → YES.** Distinct color + glyph per place type (court / property / incident / address / jurisdiction / other), with a legend in the Card.
