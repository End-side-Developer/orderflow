# Plan C Integration Tasks - Case Incidence Map

## Purpose

Convert `docs/plan-c.md` into an executable taskboard for integrating the case incidence map into OrderFlow without mixing schema, AI extraction, geocoding, UI, export, and backfill work in one risky change.

The guiding rule for implementation is: ship the smallest vertical slice that preserves auditability first, then layer UI polish and PDF export after the data contract is stable.

## Implementation Status

Last updated: 2026-05-03.

| Area | Status | Notes |
| --- | --- | --- |
| C0-C4 backend extraction/API slice | Implemented | Schema, JSONB persistence, geocode cache, Gemini place extraction, Nominatim geocoding, court fallback, and refresh endpoint are in place. Migration still needs to be applied against a live DB. |
| C5-C8 frontend map slice | Implemented | Map component, summary flow map, regenerate button, PDF-page drawer, React Leaflet v5 dependencies, and npm lockfile are wired. `npm run typecheck`, `npm run lint`, and `npm run build` pass. |
| C9 PDF export | Implemented, dependency install pending | Backend case-bundle PDF endpoint, static map renderer, HTML template, frontend download helper, and summary-page export button are wired. Runtime map/PDF quality depends on installing backend PDF extras and system libraries. |
| C10 backfill/operations | Implemented | `scripts/backfill_extracted_places.py` supports dry-run and batch processing for rows where `extracted_places IS NULL`. Root runbook notes cover migration, refresh, backfill, and PDF export dependency order. |
| C11 verification | Partial | Focused Plan C backend tests pass, and frontend lint/typecheck/build pass after locking React Leaflet v5 and removing the Google Fonts build fetch. Full repo quality is still blocked by unrelated pre-existing lint/format/test failures outside the Plan C slice. |

## Current Code Reality Check

These observations should shape the implementation order:

- `app/backend/src/orderflow_api/api/routes/page_summaries.py` currently generates summaries deterministically from persisted clauses.
- `app/backend/src/orderflow_api/api/page_summary_engine.py` defines `PageSummaryExtractor`, but the route does not currently use it for `/summaries/{document_id}/generate`.
- `PageSummaryExtractor` currently supports `openai` and `anthropic`; Plan C says Gemini, so Gemini support must be wired deliberately instead of assumed.
- `app/backend/src/orderflow_api/core/gemini_client.py` already has Gemini JSON helpers and quota guarding that should be reused.
- `app/backend/src/orderflow_api/api/routes/exports.py` supports action-plan export as markdown/json and the Plan C case-bundle PDF route.
- `Permission.EXPORT_RUN` does not exist today. Either add it intentionally or use `Permission.EXTRACTION_RUN` as Plan C allows.
- `app/frontend/src/app/document-summary/page.tsx` keeps a local `PageSummary` interface, so frontend type updates need to be done in that page and preferably centralized later.
- `app/frontend/src/components/pdf-viewer.tsx` is already a client-only PDF surface and is the right insertion point for single-page map rendering.
- The repo has existing uncommitted changes. During implementation, avoid rewriting unrelated files or formatting files outside each task scope.

## Task ID Scheme

Use `T11-C-###` for Plan C work.

- `C0` tasks are alignment and design guardrails.
- `C1` to `C4` are backend data and extraction.
- `C5` to `C8` are frontend map integration.
- `C9` is PDF export.
- `C10` is backfill and operations.
- `C11` is verification and release hardening.

## Milestone C0 - Integration Alignment

### T11-C-001 - Confirm Data Contract And Pipeline Ownership

Goal: Decide how place extraction enters the active summary pipeline.

Files to inspect or modify:

- `app/backend/src/orderflow_api/api/routes/page_summaries.py`
- `app/backend/src/orderflow_api/api/page_summary_engine.py`
- `app/backend/src/orderflow_api/core/gemini_client.py`
- `app/backend/src/orderflow_api/core/config.py`

Implementation notes:

- Keep `PageSummaryRecord.extracted_places` as the API contract.
- Reuse `PageSummaryExtractor` if it can be cleanly wired into `/summaries/{document_id}/generate`.
- If the existing deterministic route remains the default, add a dedicated place refresh path that can populate places on existing summaries.
- Treat missing AI keys as a safe no-place fallback, not a hard failure for summary generation.

Acceptance checks:

- There is one clear backend service boundary for extracting places.
- The active `/summaries/{document_id}/generate` path can eventually populate `extracted_places`.
- The refresh endpoint can populate `extracted_places` without regenerating summaries.

### T11-C-002 - Add Config Guardrails For Geocoding

Goal: Make Nominatim usage configurable and compliant.

Files to modify:

- `app/backend/src/orderflow_api/core/config.py`
- `app/backend/.env.example`
- `docs/environment-variable-policy.md` if new variable names need documentation

Implementation notes:

- Add an `ORDERFLOW_API_GEOCODER_USER_AGENT` placeholder with non-secret contact text.
- Add timeout and pacing settings only if the service needs them beyond hardcoded safe defaults.
- Do not read or expose `.env` values in logs or docs.

Acceptance checks:

- Nominatim calls use a non-empty User-Agent.
- Tests can override geocoder settings without network access.

## Milestone C1 - Schema, Persistence, And Migration

### T11-C-010 - Add ExtractedPlace Schema

Goal: Extend the typed API schema with map-ready place data.

Files to modify:

- `app/backend/src/orderflow_api/schemas/page_summaries.py`

Implementation notes:

- Add `ExtractedPlace` with the fields from Plan C.
- Use constrained literal types for `place_type` and `geocode_source`.
- Add `extracted_places: list[ExtractedPlace] = Field(default_factory=list)` to `PageSummaryRecord`.
- Keep the field backward compatible for old rows.

Acceptance checks:

- Existing summary API tests still pass with no extracted places.
- Pydantic can parse rows where `extracted_places` is missing, `None`, or `[]`.

### T11-C-011 - Add Page Summaries JSONB Column And Geocode Cache Table

Goal: Persist extracted places and reusable geocode results.

Files to create:

- `app/backend/alembic/versions/20260503_01_case_incidence_places.py`

Files to modify:

- `app/backend/src/orderflow_api/api/page_summary_persistence.py`

Implementation notes:

- Add `page_summaries.extracted_places` as nullable JSONB at the database level.
- Treat `NULL` as "not processed yet" and `[]` as "processed, no places found".
- Add `geocode_cache` keyed by `(normalized_name, state_hint)`.
- Track lat, lng, confidence, source, raw provider payload if useful, hit count, first seen, last used, and negative-cache expiry.
- Keep downgrade safe: drop cache table, then drop `extracted_places`.

Acceptance checks:

- `alembic upgrade head` creates the column and cache table.
- `alembic downgrade -1` reverses only this migration.
- `list_page_summaries()` returns `extracted_places=[]` for old/null rows.

### T11-C-012 - Add Places CRUD Helpers

Goal: Add narrow persistence functions for updating only places.

Files to modify:

- `app/backend/src/orderflow_api/api/page_summary_persistence.py`

Implementation notes:

- Add `update_page_summary_places(summary_id, extracted_places)`.
- Add `update_document_page_places(document_id, page_number, extracted_places)`.
- Add `list_documents_missing_extracted_places(limit)` or equivalent for backfill.
- Sanitize JSON strings using the same discipline used by extraction persistence if needed.

Acceptance checks:

- Updating places does not mutate `summary`, `key_points`, `important_highlights`, or `context_links`.
- Unit tests prove `NULL`, `[]`, and populated lists are handled correctly.

## Milestone C2 - Geocoding Service

### T11-C-020 - Implement Place Normalization And Deduplication

Goal: Provide deterministic normalization before cache lookup or Nominatim calls.

Files to create:

- `app/backend/src/orderflow_api/api/geocoding_service.py`

Tests to create:

- `app/backend/tests/test_geocoding_service.py`

Implementation notes:

- Normalize by lowercasing, stripping punctuation, collapsing whitespace, and preserving useful locality tokens.
- Deduplicate within a page by normalized name plus optional state hint.
- Sum `mention_count` across duplicates.
- Do not dedupe across pages; page-ordered duplicates are needed for flow mode.

Acceptance checks:

- `Delhi`, `delhi`, and `DELHI` collapse into one intra-page place.
- Mention counts are preserved.
- Cross-page repeated places remain separate records after refresh.

### T11-C-021 - Implement Geocode Cache Persistence

Goal: Avoid repeated network calls and support negative caching.

Files to create:

- `app/backend/src/orderflow_api/api/geocode_cache_persistence.py`

Tests to create or extend:

- `app/backend/tests/test_geocoding_service.py`

Implementation notes:

- Cache key: `(normalized_name, state_hint)`.
- Positive hits can be reused indefinitely unless manually pruned.
- Negative hits expire after 30 days.
- Increment `hit_count` and update `last_used_at` on every cache hit.

Acceptance checks:

- Cache hit avoids all HTTP calls.
- Expired negative cache entries allow a new HTTP attempt.
- Cache writes are idempotent for the same key.

### T11-C-022 - Implement Nominatim Client With India Bias

Goal: Geocode places safely using OpenStreetMap Nominatim.

Files to modify:

- `app/backend/src/orderflow_api/api/geocoding_service.py`

Implementation notes:

- Send `countrycodes=in`.
- Prefer query strings that include state/district hints when available.
- Use the configured User-Agent.
- Enforce 1 RPS pacing for real network misses.
- Return a place with `lat=None`, `lng=None`, and `geocode_source="none"` on failure.

Acceptance checks:

- Tests mock HTTP and assert the URL includes `countrycodes=in`.
- 5xx or timeout produces a null-coordinate result plus negative cache write.
- No test requires live network access.

### T11-C-023 - Add Court Metadata Fallback

Goal: Improve court-place pinning when raw court mentions fail.

Files to modify:

- `app/backend/src/orderflow_api/api/geocoding_service.py`
- `app/backend/src/orderflow_api/api/document_persistence.py` only if additional metadata loading is required

Implementation notes:

- For `place_type == "court"` and no Nominatim result, retry with CIS court metadata where available.
- Read court metadata from the persisted document metadata envelope, not from user-facing summaries.
- Tag fallback hits as `geocode_source="fallback_court_metadata"`.

Acceptance checks:

- A failed court geocode retries with `court_name + district + state`.
- Missing metadata does not crash refresh or generation.

## Milestone C3 - Place Extraction

### T11-C-030 - Extend Page Summary AI Prompt For Places

Goal: Ask the model for places during page summary extraction.

Files to modify:

- `app/backend/src/orderflow_api/api/page_summary_engine.py`

Implementation notes:

- Extend the prompt with Plan C's `PLACES` instructions.
- Extend the expected JSON structure with `places`.
- Parse missing `places` as `[]`.
- Validate each place through the `ExtractedPlace` schema after dedup and geocoding.
- Keep deterministic fallback returning `places=[]`.

Acceptance checks:

- Mocked AI output with `places` produces `extracted_places`.
- Old-shape AI output without `places` produces `[]` without crashing.

### T11-C-031 - Add Gemini Support To PageSummaryExtractor

Goal: Align Plan C's Gemini assumption with real code.

Files to modify:

- `app/backend/src/orderflow_api/api/page_summary_engine.py`
- `app/backend/src/orderflow_api/core/config.py` if prompt size or model settings need reuse

Implementation notes:

- Reuse `call_gemini_json` and `extract_gemini_text`.
- Respect existing Gemini quota guard.
- Keep provider-specific parsing behind small private methods.
- Do not duplicate raw urllib Gemini logic from `routes/intelligence.py`.

Acceptance checks:

- `ai_provider="gemini"` uses the shared Gemini client.
- Gemini quota errors are logged and fall back safely where appropriate.
- Tests do not hit Gemini live.

### T11-C-032 - Wire Extraction And Geocoding Together

Goal: Convert model-returned places into persisted map records.

Files to modify:

- `app/backend/src/orderflow_api/api/page_summary_engine.py`
- `app/backend/src/orderflow_api/api/geocoding_service.py`

Implementation notes:

- Deduplicate places immediately after AI parsing.
- Assign `id`, `source_page_number`, normalized name, and mention count.
- Geocode before persistence.
- Preserve non-pinnable places with null coordinates for future list views.

Acceptance checks:

- Geocoding failure still returns a valid `ExtractedPlace`.
- Page summary generation can proceed if all places fail geocoding.

## Milestone C4 - API Routes

### T11-C-040 - Include Extracted Places In Summary Responses

Goal: Make the existing summary endpoint return map data without a new read endpoint.

Files to modify:

- `app/backend/src/orderflow_api/api/page_summary_persistence.py`
- `app/backend/src/orderflow_api/api/routes/page_summaries.py`

Tests to create or extend:

- `app/backend/tests/test_api_contracts.py`

Acceptance checks:

- `GET /api/v1/summaries/{document_id}` includes `extracted_places` for each page.
- Existing clients that ignore the field continue to work.

### T11-C-041 - Add Places Refresh Endpoint

Goal: Let users generate or regenerate map data cheaply.

Files to modify:

- `app/backend/src/orderflow_api/api/routes/page_summaries.py`

Implementation notes:

- Add `POST /api/v1/summaries/{document_id}/places/refresh`.
- Gate with `Permission.EXTRACTION_RUN`.
- Re-run only place extraction and geocoding against existing summary/page text.
- Do not delete or regenerate summaries.
- Return the same `PageSummariesEnvelope` shape after refresh.

Acceptance checks:

- Refresh updates only `extracted_places` and `updated_at`.
- Refresh on a document with no summaries returns a clear 404 or empty-state error.
- Tests prove summary text is unchanged after refresh.

## Milestone C5 - Frontend Types And API Helpers

### T11-C-050 - Add Shared Frontend Place Types

Goal: Avoid duplicate map type definitions across summary page and PDF viewer.

Files to create or modify:

- `app/frontend/src/components/case-incidence-map.tsx`
- `app/frontend/src/lib/api/client.ts`
- `app/frontend/src/app/document-summary/page.tsx`

Implementation notes:

- Export `ExtractedPlace`, `PlaceType`, and `MapPlace` from the map component or move them to a dedicated API type section.
- Extend `PageSummary` with `extracted_places`.
- Normalize API payloads so missing `extracted_places` becomes `[]`.

Acceptance checks:

- `npm run typecheck` passes.
- Existing summaries without places render normally.

### T11-C-051 - Add Refresh And Export API Helpers

Goal: Keep frontend network calls centralized.

Files to modify:

- `app/frontend/src/lib/api/client.ts`

Implementation notes:

- Add `refreshSummaryPlaces(documentId)`.
- Add `downloadCaseBundlePdf(documentId, options)` later in C9.
- Reuse existing blob filename parsing for PDF downloads.

Acceptance checks:

- No direct `fetch` for these new APIs inside page components except where blob download requires the existing helper pattern.

## Milestone C6 - Reusable Map Component

### T11-C-060 - Add Leaflet Dependencies

Goal: Install the map runtime safely.

Files to modify:

- `app/frontend/package.json`
- `app/frontend/package-lock.json` or `app/frontend/pnpm-lock.yaml`, depending on the package manager used for this repo slice

Implementation notes:

- Verify React 19 compatibility before locking `react-leaflet` version.
- Keep only one lockfile authoritative if the repo standard is clarified.

Acceptance checks:

- `npm run typecheck` can resolve Leaflet types.
- No SSR crash from importing Leaflet.

### T11-C-061 - Build CaseIncidenceMap

Goal: Render flow-mode and single-page-mode maps from the same component.

Files to create:

- `app/frontend/src/components/case-incidence-map.tsx`
- `app/frontend/src/components/case-incidence-map.css` if component-scoped CSS is preferable

Implementation notes:

- Return `null` when there are no pinnable places.
- Filter out `lat == null` or `lng == null`.
- `flow` mode sorts by `source_page_number`, then stable input order.
- `single-page` mode filters by `currentPage`.
- Add `FitBounds` for one-pin and many-pin cases.
- Add marker popups with name, state/district, page number, raw snippet, and jump button.
- Add category legend.

Acceptance checks:

- Zero-place input renders nothing.
- One place renders one marker and no misleading polyline.
- Multiple places render a dashed page-order polyline.

### T11-C-062 - Implement Numbered Category Markers

Goal: Make the flow visually meaningful.

Files to modify:

- `app/frontend/src/components/case-incidence-map.tsx`
- `app/frontend/src/app/globals.css` or `case-incidence-map.css`

Implementation notes:

- Use `L.DivIcon` for markers.
- In flow mode, show page-order index.
- In single-page mode, use category glyph without flow numbering.
- Prefer inline SVG glyphs instead of remote assets.

Acceptance checks:

- Each place type has a distinct color and accessible label.
- Marker order matches page order.

## Milestone C7 - Summary Page Integration

### T11-C-070 - Render Document-Wide Flow Map

Goal: Show the case incidence flow in the summary view.

Files to modify:

- `app/frontend/src/app/document-summary/page.tsx`

Implementation notes:

- Dynamically import the map with `ssr: false`.
- Aggregate `allPlaces = summaries.flatMap((s) => s.extracted_places ?? [])`.
- Render the Card after `DocumentAdvocatesStrip`.
- Hide the Card when there are no places at all.
- `onPlaceClick` jumps to the corresponding page in the existing page detail flow.

Acceptance checks:

- Existing summary view still works with no map data.
- Clicking a marker updates `currentPage`.

### T11-C-071 - Add Regenerate Map Button

Goal: Let users backfill a map without full re-summary.

Files to modify:

- `app/frontend/src/app/document-summary/page.tsx`
- `app/frontend/src/lib/api/client.ts`

Implementation notes:

- Button calls `POST /summaries/{id}/places/refresh`.
- Show loading and error states.
- After success, replace `summaries` with the refreshed response.
- Gate visually by role/permission if the frontend has a permission helper for `EXTRACTION_RUN`; otherwise rely on backend enforcement and show a friendly error.

Acceptance checks:

- Refresh does not reset the selected view unexpectedly.
- Failed refresh leaves existing summaries intact.

## Milestone C8 - PDF Viewer Integration

### T11-C-080 - Pass Places Into PdfViewer

Goal: Allow page-by-page map filtering inside the PDF reader.

Files to modify:

- `app/frontend/src/app/document-summary/page.tsx`
- `app/frontend/src/components/pdf-viewer.tsx`

Implementation notes:

- Add `places?: ExtractedPlace[]` prop.
- Pass all summary places from the summary page.
- Keep `PdfViewer` usable without places.

Acceptance checks:

- PDF view still loads for documents with no summaries or no places.

### T11-C-081 - Add Single-Page Locations Drawer

Goal: Show only current-page places near the PDF canvas.

Files to modify:

- `app/frontend/src/components/pdf-viewer.tsx`

Implementation notes:

- Render a collapsible `<details>` block titled "Locations on this page".
- Place it near `RecommendedAdvocatesPanel` or below the canvas without stealing horizontal space.
- Suppress it if the current page has no pinnable places.

Acceptance checks:

- Changing pages changes the map contents.
- The PDF canvas remains usable on desktop and mobile.

## Milestone C9 - PDF Export With Map

### T11-C-090 - Add Backend PDF Dependencies

Goal: Prepare server-side map and PDF rendering.

Files to modify:

- `app/backend/pyproject.toml`
- `app/infra/docker-compose.yml` or backend Docker/runtime docs if system libraries are required

Implementation notes:

- Add `staticmap`, `weasyprint`, and `jinja2` if not already installed.
- Document Pango/Cairo/GDK-PixBuf system dependencies.
- Keep this task separate because dependency installation can be noisy.

Acceptance checks:

- Backend imports succeed in the local runtime.
- Quality checks do not fail due to missing optional PDF dependencies.

### T11-C-091 - Implement Static Map Renderer

Goal: Produce PNG snapshots for PDF export.

Files to create:

- `app/backend/src/orderflow_api/api/map_renderer.py`
- `app/backend/assets/map_icons/court.png`
- `app/backend/assets/map_icons/property.png`
- `app/backend/assets/map_icons/incident.png`
- `app/backend/assets/map_icons/address.png`
- `app/backend/assets/map_icons/jurisdiction.png`
- `app/backend/assets/map_icons/other.png`

Tests to create:

- `app/backend/tests/test_map_renderer.py`

Implementation notes:

- Return `bytes()` when no pinnable places exist.
- Render full-document flow map and single-page maps.
- Avoid live tile downloads in unit tests by mocking `staticmap`.

Acceptance checks:

- Empty input returns empty bytes.
- Multiple places produce non-empty PNG bytes in mocked tests.

### T11-C-092 - Add Case Bundle HTML Template

Goal: Create a PDF-ready case bundle layout.

Files to create:

- `app/backend/src/orderflow_api/templates/case_bundle.html`

Implementation notes:

- Cover page includes document metadata and optional flow map.
- Per-page section includes summary, key points, highlights, and optional page map.
- Add print CSS for page breaks and readable legal handoff formatting.

Acceptance checks:

- Template renders with and without maps.
- Template does not expose private env values or hidden metadata beyond intended document metadata.

### T11-C-093 - Add Case Bundle PDF Endpoint

Goal: Serve a downloadable PDF containing summaries and maps.

Files to modify:

- `app/backend/src/orderflow_api/api/routes/exports.py`
- `app/backend/src/orderflow_api/schemas/exports.py` if a typed request body is added

Tests to create:

- `app/backend/tests/test_exports_case_bundle.py`

Implementation notes:

- Add `POST /api/v1/exports/case-bundle/pdf`.
- Body: `document_id`, `include_per_page_maps`, `include_summary_map`.
- Gate with `Permission.EXTRACTION_RUN` unless `Permission.EXPORT_RUN` is added.
- Return `StreamingResponse` with `application/pdf`.

Acceptance checks:

- Endpoint returns PDF content type and attachment filename.
- Missing document returns 404.
- No-place document still exports a PDF without map sections.

### T11-C-094 - Add Export PDF Button

Goal: Let users download the case bundle from the summary page.

Files to modify:

- `app/frontend/src/app/document-summary/page.tsx`
- `app/frontend/src/lib/api/client.ts`

Implementation notes:

- Add an "Export PDF with map" button in the summary page header or map Card.
- Use blob download helper.
- Show loading and friendly failure state.

Acceptance checks:

- Download works when maps exist.
- Download still works when maps are absent.

## Milestone C10 - Backfill And Operations

### T11-C-100 - Add Backfill Script

Goal: Populate places for existing summaries after migration.

Files to create:

- `app/backend/scripts/backfill_extracted_places.py`

Implementation notes:

- Page through summaries where `extracted_places IS NULL`.
- Process in batches.
- Respect geocoder pacing and cache.
- Log counts, failures, skipped pages, and duration.
- Never log full judgment text.

Acceptance checks:

- Dry-run mode reports what would change.
- Batch mode can resume after failure without duplicating work.

### T11-C-101 - Add Operational Runbook Notes

Goal: Make deploy/backfill safe for future us.

Files to modify:

- `DEVELOPMENT.md` or a dedicated docs section

Implementation notes:

- Document migration, dependency, and backfill order.
- Note Nominatim rate limits and cache behavior.
- Note WeasyPrint system dependencies.

Acceptance checks:

- A teammate can run migration, refresh one document, and backfill safely from the docs.

## Milestone C11 - Verification And Quality Gates

### T11-C-110 - Backend Test Suite For Places

Goal: Cover schema, extraction, geocoding, API, and export behavior.

Tests to create or extend:

- `app/backend/tests/test_geocoding_service.py`
- `app/backend/tests/test_page_summary_engine_places.py`
- `app/backend/tests/test_api_contracts.py`
- `app/backend/tests/test_map_renderer.py`
- `app/backend/tests/test_exports_case_bundle.py`

Acceptance checks:

- `python -m pytest tests/test_geocoding_service.py -q`
- `python -m pytest tests/test_page_summary_engine_places.py -q`
- `python -m pytest tests/test_api_contracts.py -q`

### T11-C-111 - Frontend Typecheck And Manual Map QA

Goal: Ensure UI integration is stable.

Commands:

```powershell
npm run typecheck
npm run lint
npm run build
```

Manual cases:

- Multi-place document: flow map visible in summary, markers are numbered, polyline follows page order.
- Zero-place document: no map Card and no PDF-view drawer.
- Single-place document: one marker, no polyline.
- Unfindable place: persisted with null coordinates, skipped by map.
- Twenty-plus places: fit bounds works and UI remains responsive.
- Cache hit: second document mentioning the same place refreshes without repeated network geocode.

### T11-C-112 - Full Quality Gate

Goal: Run the repo quality command after Plan C tasks land.

Command:

```powershell
python scripts/quality_check.py
```

Acceptance checks:

- Frontend lint, typecheck, format check, and tests pass.
- Backend lint, format check, and tests pass.
- Any skipped live-network behavior has mocked coverage and a manual run note.

## Recommended Implementation Order

1. `T11-C-001` and `T11-C-002`
2. `T11-C-010`, `T11-C-011`, `T11-C-012`
3. `T11-C-020`, `T11-C-021`, `T11-C-022`, `T11-C-023`
4. `T11-C-030`, `T11-C-031`, `T11-C-032`
5. `T11-C-040`, `T11-C-041`
6. `T11-C-050`, `T11-C-051`
7. `T11-C-060`, `T11-C-061`, `T11-C-062`
8. `T11-C-070`, `T11-C-071`
9. `T11-C-080`, `T11-C-081`
10. `T11-C-090`, `T11-C-091`, `T11-C-092`, `T11-C-093`, `T11-C-094`
11. `T11-C-100`, `T11-C-101`
12. `T11-C-110`, `T11-C-111`, `T11-C-112`

## First Vertical Slice To Implement

For the first coding pass, do not attempt the full PDF export. Start with:

1. `T11-C-010` - schema field
2. `T11-C-011` - migration and persistence column
3. `T11-C-020` - normalize and dedupe places
4. `T11-C-021` - cache persistence
5. `T11-C-022` - mocked Nominatim client
6. `T11-C-041` - refresh endpoint
7. `T11-C-050` - frontend types
8. `T11-C-061` - map component
9. `T11-C-070` - summary flow map

This gives a demoable map while keeping PDF export as a second controlled slice.

## Non-Negotiable Safety Rules

- Never expose `.env` values.
- Do not claim place extraction is AI-backed unless the active route actually invokes the AI path.
- Do not use live Nominatim calls in automated tests.
- Do not cross-page dedupe places.
- Do not make map absence look like an error.
- Do not rewrite unrelated dirty files while implementing a task.
- Do not add `EXPORT_RUN` unless role mappings and frontend permission assumptions are updated in the same task.
