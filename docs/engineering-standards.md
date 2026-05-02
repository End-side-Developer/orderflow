# Engineering Standards

## Coding Standards

### Backend and Worker (Python)
- Use Python 3.12+.
- Use type hints on all public functions.
- Keep modules small and single-purpose.
- Avoid hidden side effects in import-time code.
- Prefer explicit dependency wiring in bootstrap code.

### Frontend (TypeScript)
- Use strict TypeScript mode.
- Prefer server components by default; use client components only when needed.
- Keep API calls in a dedicated client module.
- Keep UI components presentational where possible.

### Data and Pipelines
- Keep jobs idempotent and retry-safe.
- Log run id, input references, and output references for each job.
- Never mix parsing, business decisions, and persistence in one function.

## Naming Conventions

### Files and Modules
- Python files: snake_case.py
- TypeScript files: kebab-case.ts(x)
- Folders: kebab-case for apps, snake_case for Python package internals

### API
- Base path: /api/v1
- Resource names: plural nouns (documents, obligations, evidence)
- Query keys: snake_case

### Database
- Tables: snake_case plural
- Primary key: id
- Foreign keys: <entity>_id
- Timestamp columns: created_at, updated_at

### Workflows and Events
- Workflow names: domain_action_version (example: intake_document_v1)
- Event names: domain.entity.action (example: obligation.review.approved)

## Quality Gates

- Lint must pass before merge.
- Type checks must pass before merge.
- New endpoints require request/response schema coverage.
- New workflow steps require idempotency and retry notes.
