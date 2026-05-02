# OrderFlow Intelligence Layer

## Responsibilities
- Directive extraction from legal text.
- Entity/role/deadline parsing.
- Ambiguity and contradiction detection.
- Confidence scoring and rationale generation.

## Implemented in T11-A-010
- LangGraph interrupt-ready extraction skeleton.
- Graph state model for extraction pipeline.
- Nodes:
	- `parse_input`
	- `extract_obligations_stub`
	- `confidence_gate`
- Low-confidence interrupt placeholder branch:
	- `low_confidence_interrupt_placeholder`
- Deterministic local runner and unit tests.

## Local Run

```powershell
$env:PYTHONPATH="src"
python -m orderflow_intelligence.main --text "The respondent shall submit compliance affidavit in 7 days."
```

## Quality Commands

```powershell
$env:PYTHONPATH="src"
python -m flake8 src tests
python -m black --check src tests
python -m pytest -q tests/test_intake_graph.py
```

## Next Tasks
- T11-A-011: add OTel instrumentation baseline across request path.
- Add prompt-pack integration into `extract_obligations_stub`.
