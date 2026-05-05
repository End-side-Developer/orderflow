"""Tests for GET /public/obligations — anonymous, paginated, status-filtered.

The public endpoint wraps _safe_list_persisted() in a try/except, so DB
failures transparently fall back to an empty list. We test both paths.

Note: the route module uses `from X import Y` — patches must target the route
module's local names, not the source modules.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

import orderflow_api.api.routes.public as public_route
from orderflow_api.main import app
from orderflow_api.schemas.obligations import ObligationRecord

_BASE = "/api/v1/public/obligations"
_client = TestClient(app)
_FIXED_NOW = datetime(2026, 5, 2, 12, 0, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _no_live_obligation_store(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep public route tests independent from the developer's local DB."""
    monkeypatch.setattr(
        public_route,
        "list_persisted_obligations",
        MagicMock(return_value=[]),
    )
    monkeypatch.setattr(public_route, "list_stub_obligations", MagicMock(return_value=[]))


def _make_obligation(
    obligation_id: str = "00000000-0000-0000-0000-000000000001",
) -> ObligationRecord:
    """Return an ObligationRecord; annotate_obligations_with_risk requires attribute access."""
    return ObligationRecord(
        id=UUID(obligation_id),
        document_id=UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"),
        obligation_code="OBL-001",
        title="File compliance report",
        description="Submit the annual compliance report to the tribunal.",
        owner_hint=None,
        due_date=None,
        status="active",
        priority="medium",
        review_state="approved",
        confidence=0.9,
        confidence_annotations=None,
        escalation=None,
        citation=None,
        risk_score=None,
        risk_band=None,
        risk_factors=[],
        created_at=_FIXED_NOW,
        updated_at=_FIXED_NOW,
    )


def test_public_obligations_is_accessible_anonymously() -> None:
    """No auth credentials required."""
    resp = _client.get(_BASE)
    assert resp.status_code == 200
    body = resp.json()
    assert "total" in body["data"]
    assert "items" in body["data"]


def test_public_obligations_returns_correct_envelope_structure() -> None:
    resp = _client.get(_BASE)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert isinstance(data["total"], int)
    assert isinstance(data["items"], list)
    assert isinstance(data["redacted_count_summary"], dict)


def test_public_obligations_db_failure_returns_empty_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the DB is unavailable, the endpoint must degrade gracefully."""
    # Patch in the route module's namespace (where the names are used).
    monkeypatch.setattr(
        public_route,
        "list_persisted_obligations",
        MagicMock(side_effect=Exception("DB is down")),
    )
    monkeypatch.setattr(public_route, "list_stub_obligations", MagicMock(return_value=[]))

    resp = _client.get(_BASE)
    assert resp.status_code == 200
    assert resp.json()["data"]["total"] == 0


def test_public_obligations_limit_is_respected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    obligations = [_make_obligation(f"0000000{i}-0000-0000-0000-000000000001") for i in range(5)]
    monkeypatch.setattr(
        public_route,
        "list_persisted_obligations",
        MagicMock(return_value=[]),
    )
    monkeypatch.setattr(public_route, "list_stub_obligations", MagicMock(return_value=obligations))

    resp = _client.get(f"{_BASE}?limit=2")
    assert resp.status_code == 200
    assert resp.json()["data"]["total"] == 2


def test_public_obligations_returns_from_persisted_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    obligations = [_make_obligation("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")]
    monkeypatch.setattr(
        public_route,
        "list_persisted_obligations",
        MagicMock(return_value=obligations),
    )
    monkeypatch.setattr(public_route, "list_stub_obligations", MagicMock(return_value=[]))

    resp = _client.get(_BASE)
    assert resp.status_code == 200
    assert resp.json()["data"]["total"] == 1


def test_public_obligations_items_have_pii_redacted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each item must have a `redaction` dict (possibly empty)."""
    monkeypatch.setattr(
        public_route,
        "list_persisted_obligations",
        MagicMock(return_value=[_make_obligation()]),
    )
    monkeypatch.setattr(public_route, "list_stub_obligations", MagicMock(return_value=[]))

    resp = _client.get(_BASE)
    assert resp.status_code == 200
    for item in resp.json()["data"]["items"]:
        assert "redaction" in item, "Every public item must carry a redaction summary"
