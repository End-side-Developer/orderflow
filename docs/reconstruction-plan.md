# Restructure: Gated 5-Stage Intake Flow with Resumable, Cached AI

## Context

The current OrderFlow app has all the AI primitives (page extraction, obligation extraction, summary, geocoding, audit) but they fire **end-to-end on upload** with no gating, no progress reporting, no resumability, and **no cache reuse** — every fetch re-runs the AI. The image redesigns this into 5 explicit, gated stages where the user advances each step, AI runs only once per (document, page, prompt), and rate-limit hits are surfaced as wait-and-resume rather than failures.

This plan restructures the existing pipeline (does not rebuild) — extending `obligations` and `page_summaries` rather than introducing parallel data models, gating the existing AI calls behind a job state machine, and exposing the flow as a single wizard shell at `/case/[id]`.

## Stages (gated, in order)

| # | Stage | Trigger | Output | Cache key |
|---|---|---|---|---|
| 1 | Page extraction | "Intake" click after upload | Per-page summary + entities + dates + flow steps + place mentions + **source excerpt used** | `(document_id, page_number, prompt_version)` |
| 2 | Full-doc summary | User clicks "Continue" after pages done | Case basics, entities consolidated, petitioner/respondent, departments, full flow graph, map (conditional) | `(document_id, prompt_version)` |
| 3 | Action plan | User clicks "Generate Action Plan" after reviewing summary | Obligations extracted with `nature_of_action`, stage=`in_action_plan` | `(document_id, prompt_version)` (one-shot) |
| 4 | Review | Auto after stage 3 | Per-item Approve / Edit / Reject + per-item AI regen with user feedback | n/a (mutates obligations) |
| 5 | Dashboard | User clicks "Finalize" | Approved-only view, grouped by department | derived |

A backend job state machine enforces ordering — the user cannot skip ahead, and refreshing mid-extraction resumes from the last-completed page.

---

## Backend changes

### Schema (new Alembic migration `20260504_01_t12_intake_flow.py`)

1. **New table `extraction_jobs`** — tracks per-document multi-stage progress
   - `id`, `document_id` (unique), `stage` (enum: `pending | pages_extracting | pages_done | summary_pending | summary_done | action_plan_pending | action_plan_done | review_in_progress | finalized`)
   - `pages_total`, `pages_completed`, `current_page`, `current_page_excerpt` (JSONB — para/content the AI is actively using)
   - `last_error_code`, `last_error_message`, `retry_after_seconds`, `paused_until` (for "RPM limit, waiting Ns")
   - `current_concurrency` (int — adaptive)
   - `updated_at`, `started_at`, `finalized_at`

2. **New table `document_summaries`** — full-doc synthesis (one row per document)
   - `document_id` (unique FK), `case_basics` (JSONB: name, court, case_number, dates, directive_summary), `entities` (JSONB), `petitioner` (JSONB), `respondent` (JSONB), `departments` (JSONB), `flow_graph` (JSONB — para-to-para nodes/edges for xyflow), `map_data` (JSONB nullable — populated only when rule-based check passes), `prompt_version`, `ai_model`, `ai_provider`, `generated_at`

3. **Extend `page_summaries`** ([app/backend/src/orderflow_api/schemas/page_summaries.py](Application/orderflow/app/backend/src/orderflow_api/schemas/page_summaries.py)):
   - Add `content_hash` (sha256 of page text, for invalidation if PDF changes)
   - Add `prompt_version` (string)
   - Add `source_excerpt` (text — the actual paragraph(s) from the PDF that produced the summary, surfaced in stage-1 UI)
   - Add `ai_token_usage` (JSONB: input/output)
   - Existing unique `(document_id, page_number)` constraint becomes the cache key

4. **Extend `obligations`** ([app/backend/src/orderflow_api/api/extraction_engine.py](Application/orderflow/app/backend/src/orderflow_api/api/extraction_engine.py) and its persistence layer):
   - Add `nature_of_action` (enum: `compliance | directive | investigation | report_filing | payment | notice | other`)
   - Add `stage` (enum: `extracted | in_action_plan | review_pending | approved | rejected | edited`)
   - Add `regen_count` (int default 0), `regen_history` (JSONB — list of `{at, feedback, prev_fields}`)

### New orchestrator service

**File:** `app/backend/src/orderflow_api/api/intake_orchestrator.py` (new)

Functions:
- `start_intake(document_id)` — creates `extraction_jobs` row, kicks off Temporal workflow, returns immediately
- `get_job_status(document_id)` — returns the row + computed `percent`
- `request_summary(document_id)` — gate: `stage == pages_done`; advances to `summary_pending`, signals workflow
- `request_action_plan(document_id)` — gate: `stage == summary_done`
- `submit_review(document_id, decisions)` — bulk approve/edit/reject; advances stage
- `regenerate_action_item(obligation_id, feedback)` — surgical regen (see below)
- `finalize(document_id)` — gate: all reviewed; advances to `finalized`

### Workflow rewrite

**File:** [Application/orderflow/app/worker/src/workflows/intake.py](Application/orderflow/app/worker/src/workflows/intake.py) — replace the two stub activities with:

1. `activity_extract_page_cached(document_id, page_number, content_hash, prompt_version)`
   - SELECT from `page_summaries` first; on hit with matching hash + version → return cached
   - On miss: call `_ai_extract_page` from [page_summary_engine.py:383](Application/orderflow/app/backend/src/orderflow_api/api/page_summary_engine.py#L383), persist row, return
   - Idempotent via unique constraint
2. `activity_generate_full_summary(document_id)` — reads all `page_summaries`, calls AI to synthesize `case_basics + entities + flow_graph`, computes `map_data` rule-based (see below), upserts into `document_summaries`
3. `activity_extract_action_plan(document_id)` — calls existing `extract_obligations` + `maybe_extract_obligations_with_ai` from [ai_extraction.py:50](Application/orderflow/app/backend/src/orderflow_api/api/ai_extraction.py#L50) with extended prompt that adds `nature_of_action`; sets `stage = in_action_plan`; one-shot (skip if `action_plan_done`)
4. Stage gating uses **Temporal signals**: workflow blocks at each gate awaiting `signal_advance_to_summary`, `signal_advance_to_action_plan`, `signal_finalize` from the orchestrator endpoints.

Page-extraction loop uses an `asyncio.Semaphore(job.current_concurrency)`. On `GeminiQuotaError`:
- Catch in workflow loop
- Compute `paused_until = now + error.retry_after_seconds + 5s buffer`
- Update `extraction_jobs` row (so frontend banner can read it)
- Halve `current_concurrency` (min 1)
- Sleep until `paused_until`, retry the failed page
- After 5 consecutive successes, double `current_concurrency` back up to a cap (config `INTAKE_MAX_CONCURRENCY`, default 4)

### Map-data rule (in `activity_generate_full_summary`)

Populate `map_data` only when **all** hold:
1. `>=3` places successfully geocoded across all `page_summaries.extracted_places`
2. `>=2` distinct districts/cities (different geocode admin level)
3. Places appear across `>=2` distinct `page_summaries` rows (narrative spread, not all clustered on one page)

Otherwise `map_data = NULL` and the frontend hides the map tab.

### Per-item regeneration

`POST /api/v1/cases/{document_id}/action-plan/items/{obligation_id}/regenerate` body `{feedback: string}`:
1. Load obligation, read its citation page numbers
2. Fetch only those `page_summaries` rows from cache (no fresh AI on those pages)
3. Build focused prompt: `"Revise ONLY this single action item using the user's feedback. Pages: [...]. Current item: {...}. Feedback: {feedback}."`
4. Replace the obligation's mutable fields (title, description, owner, due_date, nature_of_action, citations)
5. Increment `regen_count`, append to `regen_history`, log audit event via existing `record_persisted_obligation_audit_event`

### New endpoints (group all under `app/backend/src/orderflow_api/api/routes/cases.py`)

- `POST /api/v1/cases/{document_id}/intake/start`
- `GET  /api/v1/cases/{document_id}/intake/status` (returns `{stage, pages_done, pages_total, current_page, current_page_excerpt, percent, error, retry_after_seconds, paused_until, current_concurrency}`)
- `GET  /api/v1/cases/{document_id}/intake/events` (SSE — pushes status updates as workflow progresses; frontend falls back to 2s poll)
- `POST /api/v1/cases/{document_id}/summary/generate` and `GET /summary`
- `POST /api/v1/cases/{document_id}/action-plan/generate` and `GET /action-plan`
- `POST /api/v1/cases/{document_id}/action-plan/items/{id}/review`
- `POST /api/v1/cases/{document_id}/action-plan/items/{id}/regenerate`
- `POST /api/v1/cases/{document_id}/finalize`
- `GET  /api/v1/cases/{document_id}/dashboard` (approved-only, department-grouped)

Old routes ([routes/intelligence.py](Application/orderflow/app/backend/src/orderflow_api/api/routes/intelligence.py), [routes/obligations.py](Application/orderflow/app/backend/src/orderflow_api/api/routes/obligations.py)) stay for now as thin shims that delegate to the orchestrator — remove in a follow-up once frontend has migrated.

---

## Frontend changes

### Wizard shell — `/case/[id]`

**New file:** `app/frontend/src/app/case/[id]/page.tsx` — single shell with:
- Horizontal **`<StageStepper />`** at top showing 5 stages, current highlighted, future locked
- Left pane: stage-specific panel (one of five components)
- Right pane: persistent **`<PdfViewer />`** ([pdf-viewer.tsx](Application/orderflow/app/frontend/src/components/pdf-viewer.tsx)) — single instance, never unmounts

**New hook:** `app/frontend/src/lib/hooks/useIntakeProgress.ts`
- Opens SSE to `/intake/events`; falls back to 2s polling on SSE error
- Returns `{stage, pageProgress, currentPageExcerpt, error, retryAfterSeconds, pausedUntil, percent}`

### Five stage panels (in `app/frontend/src/components/case/`)

1. **`PageExtractionPanel.tsx`**
   - Big progress bar: "Extracting page **5 of 16** with AI…"
   - Live source-excerpt card: shows the para AI is currently processing
   - Banner when `pausedUntil` is set: "RPM limit reached. Waiting **23s** (auto-resume)…" with countdown
   - "Continue to Summary" button enabled only when `stage == pages_done`

2. **`SummaryPanel.tsx`**
   - Case basics card (name, court, dates, directive summary)
   - Entities chips
   - Petitioner / Respondent / Departments cards
   - Flow graph (xyflow — already exists at [document-summary/[id]/flow](Application/orderflow/app/frontend/src/app/document-summary/%5Bid%5D/flow/page.tsx))
   - Map tab — **rendered only if `summary.map_data` is non-null** (uses existing `CaseIncidenceMap`)
   - "Generate Action Plan" button → POSTs `/action-plan/generate`

3. **`ActionPlanPanel.tsx`**
   - List of generated items with `nature_of_action` chip, owner, due date
   - "Continue to Review" button

4. **`ReviewPanel.tsx`**
   - Per item: Approve / Edit / Reject buttons + cited-page link (clicking scrolls right-pane PDF viewer to that page and highlights via existing `page_annotations`)
   - "Regenerate with AI" button → opens modal asking for feedback → POSTs `/regenerate` → row updates in place
   - "Finalize" button enabled when all items decided

5. **`DashboardPanel.tsx`** — Trusted View
   - Approved items grouped by department (collapsible sections)
   - "Important dates" timeline (sorted by `due_date`)
   - "Key actions" list across departments
   - Read-only; no AI buttons

### Routing migration

- `/upload/page.tsx` — on upload success, redirect to `/case/[id]` (was `/document-summary/[id]`)
- `/document-summary/[id]` — replace body with redirect to `/case/[id]`
- `/obligations` — replace body with redirect (or keep as multi-case workspace listing; not in scope)
- `/dashboard` — keep top-level workspace; per-case dashboards live inside the wizard

---

## Caching strategy summary

| Layer | Cache key | Storage | Invalidation |
|---|---|---|---|
| Page extraction | `(document_id, page_number, content_hash, prompt_version)` | `page_summaries` row | content_hash mismatch (PDF re-uploaded with edits) or prompt_version bump |
| Full-doc summary | `(document_id, prompt_version)` | `document_summaries` row | prompt_version bump |
| Action plan | `(document_id, prompt_version)` | `obligations` rows where `stage in (in_action_plan, approved, ...)` | one-shot — only regen via per-item endpoint |
| Per-item regen | manual (`regen_count` increments) | mutates obligation in place | user-driven |

Token-saving guarantee: every AI call site checks cache before calling provider. The `_GeminiQuotaGuard` already tracks RPM/TPM; it now also drives adaptive concurrency in the orchestrator.

---

## Critical files to modify

- [app/backend/src/orderflow_api/api/page_summary_engine.py](Application/orderflow/app/backend/src/orderflow_api/api/page_summary_engine.py) — add cache check in `extract_page_summaries` (lines 251-342); persist `source_excerpt`, `content_hash`, `prompt_version`
- [app/backend/src/orderflow_api/api/ai_extraction.py](Application/orderflow/app/backend/src/orderflow_api/api/ai_extraction.py) — extend prompt to include `nature_of_action`; reuse `maybe_extract_obligations_with_ai` (line 50)
- [app/backend/src/orderflow_api/core/gemini_client.py](Application/orderflow/app/backend/src/orderflow_api/core/gemini_client.py) — `_GeminiQuotaGuard` (lines 132-276) exposes `current_concurrency` setter/getter; orchestrator drives it
- [app/backend/src/orderflow_api/api/extraction_engine.py](Application/orderflow/app/backend/src/orderflow_api/api/extraction_engine.py) — add `nature_of_action` and `stage` to obligation dict
- [app/worker/src/workflows/intake.py](Application/orderflow/app/worker/src/workflows/intake.py) — full rewrite (signals, semaphore, retry-after, cache-aware activities)
- [app/frontend/src/app/upload/page.tsx](Application/orderflow/app/frontend/src/app/upload/page.tsx) — redirect target only
- New: `app/backend/src/orderflow_api/api/intake_orchestrator.py`, `app/backend/src/orderflow_api/api/routes/cases.py`, `app/backend/alembic/versions/20260504_01_t12_intake_flow.py`
- New: `app/frontend/src/app/case/[id]/page.tsx`, `app/frontend/src/components/case/{StageStepper,PageExtractionPanel,SummaryPanel,ActionPlanPanel,ReviewPanel,DashboardPanel}.tsx`, `app/frontend/src/lib/hooks/useIntakeProgress.ts`

---

## Verification

1. **Cache hit test (unit)** — call `activity_extract_page_cached` twice with same args; assert second call makes zero AI calls (mock provider) and returns identical row
2. **Cache invalidation test** — change `prompt_version`; assert second call hits AI
3. **Adaptive concurrency test** — simulate `GeminiQuotaError` mid-extraction; assert `current_concurrency` halves, `paused_until` set, retry succeeds, concurrency recovers after 5 successes
4. **Resumability test (integration)** — start intake on a 16-page PDF, kill the worker after page 8 completes, restart worker, assert it resumes from page 9 (not 1) using cached pages 1-8
5. **Stage gating test** — try POSTing `/summary/generate` while `stage == pages_extracting` → expect 409
6. **Per-item regen test** — reject an item with feedback "should be the Health Department, not Education"; assert AI is called only with the cited pages' summaries (not the whole document) and only that item's fields change
7. **Map-rule test** — synthetic page summaries with 2 places → `map_data` is NULL; with 5 places across 4 districts on 3 different pages → `map_data` populated
8. **End-to-end manual** — upload a real court order PDF, walk all 5 stages, refresh page mid-extraction (resumes), trigger an artificial RPM error (banner shows wait), reject one item with feedback (regenerates), finalize, confirm Dashboard shows only approved items grouped by department
9. **Token-saving manual** — re-upload the **same** PDF → confirm zero AI calls in the worker logs (full cache reuse)
