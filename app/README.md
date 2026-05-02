# App Monorepo Boundaries

This folder contains all implementation services for Theme 11 (OrderFlow).

## Service Boundaries

- frontend: Reviewer-facing web UI (Next.js App Router).
- backend: Domain API and persistence layer (FastAPI).
- worker: Long-running orchestration and workflow workers (Temporal, LangGraph).
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
- Next in queue: T11-B-008 (workflow polling, escalation triggers, and reviewer audit trail).
