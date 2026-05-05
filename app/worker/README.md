# OrderFlow Worker Service

Purpose: execute durable workflows and long-running background logic.

## Responsibilities

- Start and manage Temporal workflows.
- Run LangGraph extraction and review state transitions.
- Coordinate retry-safe workflow steps.
- Emit audit events and observability spans.
- Enforce durable waits for human-triggered summary, action-plan, and finalize gates.
- Reuse valid cached page summaries after retry or worker restart.

## Non-Responsibilities

- Do not own public HTTP APIs.
- Do not render UI.
- Do not store business state outside approved data stores.

## Planned Structure

- src/workflows/
- src/activities/
- src/graph/
- src/bootstrap/

## Implemented in T11-A-009

- Temporal workflow skeleton:
	- `orderflow-intake-workflow`
	- flow: `start -> translate_document_if_needed_activity -> activity_extract_page_cached (all requested pages) -> pages_done -> gated summary -> gated action_plan`
	- before scheduling page extraction, `activity_list_completed_pages` finds valid cached page summaries and the workflow skips those pages so a resumed run continues from incomplete pages.
	- default run waits durably at `pages_done` until the `advance_to_summary` Temporal signal is received; controlled tests can bypass the wait with `auto_advance_summary=true`.
	- after summary generation, the workflow waits durably at `summary_done` until the `advance_to_action_plan` Temporal signal is received; controlled tests can bypass the wait with `auto_advance_action_plan=true`.
	- after action-plan generation, the workflow waits durably for the backend-validated `finalize` Temporal signal; controlled tests can bypass the wait with `auto_finalize_review=true`.
- Worker runtime entrypoint in `src/orderflow_worker/main.py`.
- Local queue and Temporal host/namespace config via `.env`.

## Local Run

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
python -m orderflow_worker.main
```

## Restart Recovery During Page Extraction

If the worker stops while a document is in `pages_extracting`, restart only the
worker and leave Temporal, Postgres, Redis, MinIO, and the backend running.
Temporal keeps the workflow history; the backend database keeps completed page
summaries and extraction job progress.

```powershell
cd app/worker
python -m orderflow_worker.main
```

Recovery flow:

- The existing `orderflow-intake-workflow` continues from Temporal history.
- `activity_list_completed_pages` runs before new page extraction work and skips page summaries already saved for the same document, page number, content hash, prompt version, model, and provider.
- Only incomplete, stale, or failed pages are scheduled again through `activity_extract_page_cached`.
- If a rate-limit pause was recorded, the status payload exposes `is_paused`, `retry_after_seconds`, `paused_until`, and a safe `next_action`; the workflow sleeps, lowers concurrency, and retries the same failed page after the pause.
- Poll `GET /api/v1/cases/<document_id>/intake/status` or keep the case UI open to confirm `pages_completed` advances. Reaching `pages_done` means the page-recovery step is complete and the user can request summary generation.

Do not delete page summaries or start a second workflow for the same document as
a recovery step. Use `bypass_cache=true` only for an intentional manual
regeneration, not for a normal worker restart.

## Quality Commands

```powershell
python -m pytest -q tests
python -m flake8 --jobs 1 src tests
```

Useful focused checks for the gated flow:

```powershell
python -m pytest -q tests\test_intake_activity_smokes.py::test_page_activity_second_same_request_uses_cache_without_provider
python -m pytest -q tests\test_intake_activity_smokes.py::test_worker_restart_resumability_simulation_skips_completed_pages
```
