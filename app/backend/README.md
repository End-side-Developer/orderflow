# OrderFlow Backend

Stack: FastAPI + Pydantic settings.

## Responsibilities
- Document intake and parsing orchestration.
- Obligation CRUD and lifecycle APIs.
- Evidence validation and escalation services.
- Audit/event logging.
- Gated case-stage transitions for the verified action-plan flow.
- Cache-aware page summary, document summary, and action-plan persistence.
- Trusted dashboard filtering so only human-approved or edited records are exposed after finalization.

## Implemented in T11-A-002
- Runnable FastAPI app skeleton in `src/orderflow_api`.
- Typed config loader (`core/config.py`).
- Structured success/error response envelope.
- Request id middleware (`x-request-id`).
- Health endpoints:
	- `/health`
	- `/api/v1/health`

## Implemented in T11-A-007
- API contract routes:
	- `POST /api/v1/documents`
	- `GET /api/v1/documents/{document_id}`
	- `GET /api/v1/obligations?document_id=...`
- Typed request/response schemas for document and obligation contracts.
- Stub-safe in-memory repository layer to unblock frontend integration.

## Implemented in T11-A-008
- Upload and persistence route:
	- `POST /api/v1/documents/upload`
- MinIO object storage adapter with automatic bucket bootstrap.
- Metadata persistence to PostgreSQL `documents` table:
	- `object_key`, `checksum_sha256`, `source_file_size`, `source_file_type`.
- Persisted fetch fallback in `GET /api/v1/documents/{document_id}`.

## Implemented in T11-A-009
- Intake workflow start route:
	- `POST /api/v1/workflows/intake/start`
- Temporal client bootstrap via environment-driven settings.
- Workflow run persistence table (`workflow_runs`) and document linkage (`documents.workflow_run_id`).
- API contract coverage for workflow start route in backend tests.

## Implemented in T11-A-011
- Backend request lifecycle tracing baseline with OpenTelemetry SDK.
- OTLP exporter wiring via `ORDERFLOW_OTEL_ENDPOINT` for collector routing.
- Request correlation headers:
	- accepts and echoes `x-request-id`
	- emits `x-trace-id` for trace-to-request debugging.
- Trace attributes include request method/path and frontend correlation metadata headers.

## Implemented in T11-B-001
- Intake extraction execution route:
	- `POST /api/v1/extractions/intake/run`
- Deterministic extraction engine for text-readable documents:
	- clause segmentation
	- directive-based obligation extraction
	- due-date and priority heuristics
- Persistence wiring for `clauses` and `obligations` tables.
- Obligations route support for persisted extraction output.
- API contract tests for extraction run and persisted obligations response.

## Implemented in T11-B-002
- PDF-first parsing path in extraction decode layer.
- Docling parser integration for persisted PDF documents.
- Deterministic fallback PDF text extraction for local environments without Docling.
- Unit tests validating Docling-preferred and fallback decode behavior.

## Implemented in T11-B-003
- Clause segmentation fidelity improvements:
	- page number awareness
	- absolute span offsets for citation mapping
	- stable clause span token format (`p{page}:c{index}:{start}-{end}`)
- Citation enrichment in persisted obligations:
	- `clause_index`, `span_start`, `span_end` metadata
- Clause retrieval helper route with filters:
	- `GET /api/v1/clauses?document_id=...&page_number=...&clause_span=...`
- Backend contract and engine tests for page/span citation indexing and retrieval filters.

## Implemented in T11-B-004
- Structured obligation extractor v1 enhancements in extraction engine:
	- owner/action/deadline field extraction
	- explicit date parsing (`by 25/12/2099`-style deadlines)
	- structured title generation from extracted action phrase
- Confidence annotation model for extracted obligations:
	- weighted component signals
	- rationale notes
	- extraction signal payload
- Confidence annotation persistence via obligations metadata and API schema mapping.
- Backend tests covering structured extraction and confidence annotation serialization.

## Implemented in T11-B-006
- Workflow status routes for orchestration-aware dashboards:
	- `GET /api/v1/workflows/intake/status?document_id=...`
	- `GET /api/v1/workflows/runs/{run_id}`
- Workflow persistence helper support for latest-run lookup by document.
- Contract test coverage for new workflow status routes and OpenAPI path exposure.

## Implemented in T11-B-007
- Reviewer decision update route for obligation triage:
	- `PATCH /api/v1/obligations/{obligation_id}`
- Typed update schema and single-obligation envelope contract for UI actions.
- Persistence support for obligation update in both persisted and in-memory stub paths.
- Contract test coverage for obligation update route and OpenAPI path exposure.

## Implemented in T11-B-009
- Indian eCourts intake adapter route:
	- `POST /api/v1/documents/intake/indian-ecourts`
- One-input online lookup prefill route:
	- `POST /api/v1/documents/intake/indian-ecourts/lookup`
- CCMS + optional CIS envelope normalization into document metadata.
- Read-only downstream integration marker persisted with each intake document.
- Contract tests for both CCMS+CIS and CCMS-only payloads.
- Lookup flow notes:
	- Resolves Delhi High Court public judgment links from URL/token/case-id patterns.
	- eCourts case-status forms are captcha-protected, so this lookup uses public judgment links and PDF heuristics.

## Implemented in New Gated Case Flow

- Duplicate document upload guard:
	- `POST /api/v1/documents/upload` returns `409 duplicate_document` with the existing document id when the checksum already exists.
- Case-stage orchestration routes:
	- `POST /api/v1/cases/{document_id}/intake/start`
	- `GET /api/v1/cases/{document_id}/intake/status`
	- `POST /api/v1/cases/{document_id}/summary/generate`
	- `GET /api/v1/cases/{document_id}/summary`
	- `POST /api/v1/cases/{document_id}/action-plan/generate`
	- `GET /api/v1/cases/{document_id}/action-plan`
	- `POST /api/v1/cases/{document_id}/action-plan/items/{obligation_id}/review`
	- `POST /api/v1/cases/{document_id}/action-plan/items/{obligation_id}/regenerate`
	- `POST /api/v1/cases/{document_id}/finalize`
	- `GET /api/v1/cases/{document_id}/dashboard`
- Gate behavior:
	- Summary generation requires `pages_done`.
	- Action-plan generation requires `summary_done`.
	- Finalization requires every action-plan item to be reviewed and at least one item approved or edited.
	- Dashboard requires `finalized` and filters server-side to approved or edited action-plan records.
- Cache behavior:
	- Page summaries use content hash, prompt version, model, and provider context.
	- Document summaries are cached per document and generation context.
	- Action plans are cached as obligation lifecycle rows; per-item regeneration uses only cached cited page summaries.
- Manual verification on 2026-05-04 reached `finalized` with 18 approved action-plan records and dashboard total 18.

## Implemented in Current Iteration (Multi-AI Extraction)
- Intake extraction request now supports optional AI config payload:
	- `POST /api/v1/extractions/intake/run`
	- request field: `ai` (`enabled`, `provider`, `model`, `api_key`, `temperature`, `max_obligations`)
- Provider abstraction in backend extraction path:
	- `mock`
	- `openai`
	- `anthropic`
- Runtime metadata returned in extraction result:
	- `extraction_mode` (`deterministic`, `ai`, `ai_fallback`)
	- `ai_provider`, `ai_model`, `ai_reason`
- Deterministic fallback stays active when AI is disabled, misconfigured, or returns no usable obligations.

## AI Configuration
- Backend defaults (internal testing) are driven by env vars:
	- `ORDERFLOW_AI_ENABLED_DEFAULT`
	- `ORDERFLOW_AI_ALLOW_USER_OVERRIDE`
	- `ORDERFLOW_AI_DEFAULT_PROVIDER`
	- `ORDERFLOW_AI_DEFAULT_MODEL`
	- `ORDERFLOW_AI_OPENAI_API_KEY`
	- `ORDERFLOW_AI_ANTHROPIC_API_KEY`
	- `ORDERFLOW_AI_TIMEOUT_SECONDS`
	- `ORDERFLOW_AI_MAX_CLAUSES`
- If `ORDERFLOW_AI_ALLOW_USER_OVERRIDE=true`, request-level `ai` options may override provider/model/key for live testing.
- If provider key is missing (OpenAI/Anthropic), extraction remains safe and falls back to deterministic mode.

## Local Run

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
# Optional: install PDF parser stack for higher-fidelity extraction.
pip install -e ".[dev,pdf]"
python -m uvicorn orderflow_api.main:app --host 0.0.0.0 --port 8000 --reload
```

## Database Migrations

```powershell
python -m alembic -c alembic.ini upgrade head
python -m alembic -c alembic.ini downgrade -1
```

## Quality Commands

```powershell
python -m flake8 src tests
python -m black --check src tests
python -m pytest -q
```

## Next Tasks
- T11-B-008: workflow polling, escalation triggers, and reviewer audit trail.
- T11-B-010: similar-case memory clustering and reviewer recommendation wiring.
