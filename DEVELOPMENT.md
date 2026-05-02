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
- Current roadmap is synced to README pillars:
	- Verified obligation ledger
	- Proof-gated completion
	- Risk and escalation engine
- Next in queue:
	- T11-B-008 (workflow polling, escalation triggers, and reviewer audit trail)
	- T11-B-009 (CCMS PDF + CIS metadata intake adapter)
	- T11-B-010 (similar-case memory clustering and reviewer recommendations)

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
