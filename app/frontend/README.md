# OrderFlow Frontend

Stack: Next.js App Router + TypeScript.

## Responsibilities

- Judgment upload workspace.
- Obligation Kanban/timeline board.
- Risk and escalation dashboards.

## Implemented in T11-A-003

- Next.js shell scaffold with App Router.
- Global layout and top navigation.
- Core shell pages:
  - `/`
  - `/upload`
  - `/obligations`
  - `/risk`
- API client utility in `src/lib/api/client.ts`.

## Implemented in T11-A-011

- Frontend request correlation metadata in API client:
  - sends `x-request-id`
  - sends `x-client-service`
  - sends `x-client-path`
- Enables trace correlation from frontend-triggered requests into backend OTel spans.

## Implemented in T11-B-005

- Upload workspace wired to backend intake flow:
  - `POST /api/v1/documents/upload`
  - `POST /api/v1/extractions/intake/run`
- Obligations board wired to persisted backend data:
  - `GET /api/v1/obligations?document_id=...`
- Extraction review utility styling for forms, board columns, cards, and status pills.

## Implemented in T11-B-006

- Upload flow now starts workflow orchestration after extraction:
  - `POST /api/v1/workflows/intake/start`
- Risk dashboard wired to workflow and obligations data:
  - `GET /api/v1/workflows/intake/status?document_id=...`
  - `GET /api/v1/workflows/runs/{run_id}`
- Obligations page deep-link to risk board with workflow/document context propagation.

## Implemented in T11-B-007

- Obligations reviewer action controls wired to backend updates:
  - approve/reject via `PATCH /api/v1/obligations/{obligation_id}`
  - owner reassignment via same update contract
- Citation drill-down on each obligation card:
  - uses `GET /api/v1/clauses?document_id=...&clause_span=...`
- In-card state refresh after reviewer actions for immediate UI feedback.

## Implemented in Current Iteration (AI Control Surface)

- Upload workspace supports AI mode controls for live extraction testing:
  - `backend_default` (use backend env defaults)
  - `deterministic_only` (force non-AI extraction)
  - `mock`, `openai`, `anthropic`
- Optional override fields on upload form:
  - model
  - API key
  - temperature
  - max obligations
- These controls are sent to backend in `POST /api/v1/extractions/intake/run` as `ai` options.
- Backend still applies deterministic fallback when AI fails or is disabled.

## Local Run

```powershell
npm install
npm run dev
```

## Quality Commands

```powershell
npm run lint
npm run typecheck
npm run format:check
npm run test
```

## Next Tasks

- Wire related-case panel to a dedicated backend top-k similarity endpoint when B010 service is available.
- Enforce completion verification server-side in obligation update path for full B011 parity.
- Expand verifier capture with structured evidence attachments and immutable verification event rendering.
