# App Monorepo Boundaries

This folder contains all implementation services for Theme 11 (OrderFlow).

## Service Boundaries

- frontend: Reviewer-facing web UI and `/case/[id]` gated wizard (Next.js App Router).
- backend: Domain API, gate checks, cache persistence, and trusted dashboard filtering (FastAPI).
- worker: Long-running gated orchestration and cached extraction workers (Temporal, LangGraph).
- intelligence: Extraction assets, prompts, and evaluation helpers.
- data-pipelines: Batch and ingestion jobs.
- infra: Local runtime stack and deployment configs.
- shared: Cross-service contracts and schema artifacts.

## Boundary Rules

- frontend talks to backend over HTTP only.
- worker talks to backend/db/queue, never to frontend directly.
- intelligence has no direct network side effects; worker calls it.
- data-pipelines write via defined backend/db contracts.
- shared is import-only reference material and generated contracts.

## Current Delivery Stage

- T11-A-001 completed: boundaries, standards, and env templates.
- T11-A-002 completed: backend skeleton and health endpoints.
- T11-A-003 completed: frontend shell and API client utility.
- T11-A-004 completed: local infra compose stack and observability baseline.
- T11-A-005 completed: lint/format/test automation, pre-commit, CI skeleton.
- T11-A-006 completed: Alembic baseline plus core schema migration v1.
- T11-A-007 completed: v1 document and obligation contract routes with tests.
- T11-A-008 completed: MinIO upload adapter with DB metadata persistence.
- T11-A-009 completed: Temporal intake workflow skeleton with run tracking API hook.
- T11-A-010 completed: LangGraph interrupt-ready skeleton with deterministic tests.
- T11-A-011 completed: backend request spans and frontend request correlation metadata.
- T11-A-012 completed: phase-a vertical-slice runbook and troubleshooting guide.
- T11-B-001 completed: intake extraction run API with clause and obligation persistence.
- T11-B-002 completed: PDF-first Docling parsing with deterministic local fallback.
- T11-B-003 completed: citation indexing with page/span fidelity and clause retrieval helpers.
- T11-B-004 completed: structured extractor v1 with confidence component annotations.
- T11-B-005 completed: upload to extraction trigger and obligation board wiring.
- T11-B-006 completed: workflow run status integration and risk board stream wiring.
- T11-B-007 completed: citation drill-down and reviewer decision actions.
- New gated flow completed through manual E2E: upload or duplicate reuse, Intake,
  cached page extraction, summary, action plan, mandatory item review, finalize,
  and approved-only trusted dashboard.
- Current quality caveat: root `python scripts/quality_check.py` is not green
  because frontend Prettier, backend flake8, and backend Black cleanup remain.

## Current Runtime Flow

1. Frontend uploads a judgment and opens `/case/[id]`.
2. Backend starts and gates case stages under `/api/v1/cases/{document_id}`.
3. Worker runs the Temporal intake workflow and skips valid cached page summaries.
4. Backend allows summary generation only after pages are done.
5. Backend allows action-plan generation only after summary is done.
6. Frontend submits human review decisions for every action-plan item.
7. Backend finalizes only after all items are reviewed and at least one is approved or edited.
8. Dashboard returns only approved or edited action records for finalized cases.
