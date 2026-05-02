# OrderFlow Worker Service

Purpose: execute durable workflows and long-running background logic.

## Responsibilities

- Start and manage Temporal workflows.
- Run LangGraph extraction and review state transitions.
- Coordinate retry-safe workflow steps.
- Emit audit events and observability spans.

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
	- flow: `start -> parse_stub_activity -> done`
- Worker runtime entrypoint in `src/orderflow_worker/main.py`.
- Local queue and Temporal host/namespace config via `.env`.

## Local Run

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
python -m orderflow_worker.main
```
