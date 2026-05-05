# Development Startup Guide

This guide is the root-level developer handoff for OrderFlow.

## Current Status

- T11-A-001 is complete (boundaries, standards, env policy, templates).
- T11-A-002 to T11-A-011 are complete (service skeletons, infra, data contracts, workflow, intelligence, observability).
- T11-A-012 is complete (vertical-slice runbook and troubleshooting flow).
- T11-B-001 is complete (intake extraction run with clause and obligation persistence).
- T11-B-002 is complete (PDF-first Docling parsing with deterministic local fallback).
- T11-B-003 is complete (citation indexing with page/span fidelity and clause retrieval helpers).
- T11-B-004 is complete (structured extractor v1 with confidence component annotations).
- T11-B-005 is complete (upload to extraction trigger and obligation board wiring).
- T11-B-006 is complete (workflow run status integration and risk board stream wiring).
- T11-B-007 is complete (citation drill-down and reviewer decision actions).
- The new gated case flow is implemented and manually verified through:
	upload/duplicate reuse, Intake, cached page extraction, summary generation,
	action-plan generation, per-item human review, finalization, and trusted dashboard.
- Current roadmap is synced to README pillars:
	- Verified obligation ledger
	- Proof-gated completion
	- Risk and escalation engine
- Next in queue:
	- T11-B-010 (similar-case memory clustering and reviewer recommendations)
	- Final quality-gate cleanup for frontend Prettier, backend flake8, and backend Black.

## Read First

1. docs/engineering-standards.md
2. docs/environment-variable-policy.md
3. app/README.md

## Local Startup Target (Current Slice)

When skeleton services are added, startup flow is:

1. Start infra stack in app/infra.
2. Start backend service in app/backend.
3. Start worker service in app/worker.
4. Start frontend in app/frontend.

## One-Command Local Startup

From `theme-11-orderflow` run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-orderflow.ps1
```

The launcher starts Temporal, infra, backend, worker, and frontend, and skips any step that is already running.

## Gated Case Flow Startup

For the current "Court Judgment to Verified Action Plan" flow, keep all four
runtime layers up:

1. Infra and Temporal from `app/infra`.
2. Backend API from `app/backend`.
3. Temporal worker from `app/worker`.
4. Frontend reviewer workspace from `app/frontend`.

Manual startup:

```powershell
cd app/infra
docker compose up -d

cd ..\backend
python -m alembic -c alembic.ini upgrade head
python -m uvicorn orderflow_api.main:app --host 0.0.0.0 --port 8000 --reload

cd ..\worker
python -m orderflow_worker.main

cd ..\frontend
npm run dev
```

Open `http://localhost:3000/upload`, upload a judgment, and continue in
`/case/<document_id>`. Re-uploading the same PDF should return
`409 duplicate_document` with the existing document id instead of starting a
new extraction.

## Gated Case Flow Verification

Use one small sample PDF and keep notes to ids, counts, stages, and route
results. Do not paste full judgment text into logs or docs.

Expected happy path:

1. `POST /api/v1/documents/upload`.
2. `POST /api/v1/cases/<document_id>/intake/start`.
3. Poll `GET /api/v1/cases/<document_id>/intake/status` until `pages_done`.
4. `POST /api/v1/cases/<document_id>/summary/generate`.
5. Poll status until `summary_done`, then fetch `GET /api/v1/cases/<document_id>/summary`.
6. `POST /api/v1/cases/<document_id>/action-plan/generate`.
7. Poll status until `action_plan_done`, then fetch `GET /api/v1/cases/<document_id>/action-plan`.
8. Review every item through `POST /api/v1/cases/<document_id>/action-plan/items/<obligation_id>/review`.
9. `POST /api/v1/cases/<document_id>/finalize`.
10. Confirm `GET /api/v1/cases/<document_id>/dashboard` returns only approved or edited records.

Manual evidence from 2026-05-04: sample
`docs/samples/court-cases/delhi-hc-wpc-8524-2025-judgment-05-02-2026.pdf`
completed through `finalized` with `pages_completed/pages_total=1/1`, 18
approved action-plan records, and dashboard total 18.

Current quality caveat: `python scripts/quality_check.py` is not green. The
latest root run passed frontend lint/typecheck, then reported frontend Prettier
failures, backend flake8 failures, backend Black formatting failures, and timed
out before backend tests were reached.

## Worker Mid-Extraction Recovery

OrderFlow page extraction is designed to recover from a worker restart without
re-running completed pages. Keep Postgres and Temporal running, because the
workflow history lives in Temporal and completed page summaries live in the
database.

1. Stop only the worker process if you are simulating a crash or applying a worker change.
2. Start the worker again:

```powershell
cd app/worker
python -m orderflow_worker.main
```

3. Watch the case status from the backend or case UI:

```powershell
curl http://localhost:8000/api/v1/cases/<document_id>/intake/status
```

Expected behavior:

- Temporal resumes the existing `orderflow-intake-workflow`; do not create a new workflow manually.
- Before scheduling page work, `activity_list_completed_pages` reads persisted page summaries and skips pages whose `content_hash`, `prompt_version`, `ai_model`, and `ai_provider` still match the current run.
- If the worker stopped while a page activity was in flight, Temporal retries that page after the activity failure or timeout. Already saved page summaries are reused.
- If status shows `is_paused=true`, `retry_after_seconds`, or `paused_until`, wait for the rate-limit pause. The workflow will resume and retry the failed page with reduced concurrency.
- If status is `pages_done`, recovery is complete. Continue with `POST /api/v1/cases/<document_id>/summary/generate`.

Recovery guardrails:

- Do not clear Postgres, Temporal, or page-summary rows during recovery.
- Do not use `bypass_cache=true` unless the goal is to intentionally regenerate cached units.
- If status shows a user-facing error such as `ocr_required`, fix the source document issue first; restarting the worker alone will not make an unreadable PDF extractable.

## Service Owners

- frontend: UI and reviewer flows
- backend: API and persistence
- worker: workflow and orchestration
- intelligence: extraction logic assets
- data-pipelines: ingestion and batch tasks

## Language and Translation

OrderFlow supports multi-language court documents (Hindi, Tamil, Telugu, Kannada, Malayalam, Marathi).

### Components

- **Language Detection**: `app/backend/src/orderflow_api/core/language_service.py` (uses `langdetect`)
- **Translation Service**: `app/backend/src/orderflow_api/core/translation_service.py` (LibreTranslate API client)
- **LibreTranslate Service**: Docker container in `app/infra/docker-compose.yml`

### Local Setup

```bash
# 1. Start LibreTranslate (included in docker-compose)
cd app/infra
docker-compose up -d libretranslate

# 2. Verify it's running
curl http://localhost:5000/health  # Should return {"status":"OK"}

# 3. Install Python dependencies
cd ../backend
pip install langdetect aiohttp tenacity

# 4. Run database migration
alembic upgrade head

# 5. Run language tests
pytest tests/test_language_detection.py tests/test_translation_service.py -v
```

### Configuration

Add to `.env` or environment:

```env
ORDERFLOW_TRANSLATION_SERVICE_URL=http://localhost:5000
ORDERFLOW_TRANSLATION_TIMEOUT_SECONDS=30
ORDERFLOW_TRANSLATION_CACHE_ENABLED=true
```

### Testing Language Support

```python
# Test detection
from orderflow_api.core.language_service import detect_language

result = detect_language("यह एक न्यायालय का निर्णय है।")
print(f"Detected: {result.detected_language} (confidence: {result.confidence})")

# Test translation (async)
import asyncio
from orderflow_api.core.translation_service import TranslationService, TranslationServiceConfig

async def test_translate():
    config = TranslationServiceConfig(service_url="http://localhost:5000")
    service = TranslationService(config)
    result = await service.translate("नमस्ते", "hi", "en")
    print(f"Translated: {result}")

asyncio.run(test_translate())
```

### Action Plan Export

Use the backend export endpoint to download a translated action plan:

```bash
curl -L "http://localhost:8000/api/v1/exports/action-plan?document_id=<uuid>&language=hi&format=markdown" -o action-plan-hi.md
curl -L "http://localhost:8000/api/v1/exports/action-plan?document_id=<uuid>&language=en&format=json" -o action-plan-en.json
```

### Documentation

- [docs/language-support.md](docs/language-support.md) — Full user guide and troubleshooting


## Plan C Case Incidence Map

Plan C adds page-level `extracted_places`, cached Nominatim geocoding, and frontend Leaflet maps.

### Deployment Order

1. Configure backend geocoder environment variables from `app/backend/.env.example`.
2. Apply the backend migration:

```powershell
cd app/backend
alembic upgrade head
```

3. Install frontend map dependencies and commit the updated lockfile:

```powershell
cd app/frontend
npm.cmd install leaflet@^1.9.4 react-leaflet@^5.0.0 @types/leaflet@^1.9.12
```

4. Restart backend and frontend services.
5. For one document, generate summaries and use "Regenerate map" from the summary page.
6. Backfill older summaries only after the single-document refresh path is verified.
7. Install backend PDF extras before enabling case-bundle PDF export in a shared runtime:

```powershell
cd app/backend
python -m pip install -e ".[pdf]"
```

WeasyPrint also needs native Pango/Cairo/GDK-PixBuf libraries on the host or image. Keep that as an image/runtime dependency, not an `.env` value.

### Backfill Existing Summaries

Dry-run first. The script logs document IDs, page numbers, and text lengths, but never logs full judgment text.

```powershell
cd app/backend
python -m scripts.backfill_extracted_places --dry-run --limit 50
python -m scripts.backfill_extracted_places --limit 200 --batch-size 20
```

The script only processes rows where `page_summaries.extracted_places IS NULL`. Empty lists mean the page was processed and no places were found. Failed rows remain `NULL` so a later run can retry them.

### Operational Notes

- Nominatim calls must include a non-empty User-Agent and are paced through backend settings.
- Positive geocode cache hits are reused; negative cache hits expire after 30 days.
- Live geocoding should not be used in unit tests; mock the Nominatim client or cache layer.
- PDF export uses `POST /api/v1/exports/case-bundle/pdf`, `staticmap` for map snapshots, and WeasyPrint for the full HTML-to-PDF render. If optional PDF dependencies are missing, the route falls back to a minimal PDF rather than breaking document handoff.

## Notes

- Keep all env values aligned with each service `.env.example` file.
- Use ticket IDs for branch and commit naming.
- Keep ticket language aligned to README:
	- "judgment to verified action"
	- "proof-gated completion"
	- "risk and escalation loop"

## One-Command Quality Gate

From `theme-11-orderflow` run:

```powershell
python scripts/quality_check.py
```

Enable the pre-push quality hook:

```powershell
python -m pre_commit install --hook-type pre-push
```
