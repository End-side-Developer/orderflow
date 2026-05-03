"""Tests for /advocates/* endpoints.

Covers: public directory listing, profile detail, pending queue,
verification/rejection, and permission enforcement.
"""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

import orderflow_api.api.user_persistence as user_persistence
from orderflow_api.main import app
from orderflow_api.schemas.advocates import AdvocateProfileRecord
from tests.conftest import bearer, make_user

_BASE = "/api/v1/advocates"
_client = TestClient(app)

_FIXED_NOW = datetime(2026, 5, 2, 12, 0, 0, tzinfo=UTC)
_ADVOCATE_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
_JUDGE_ID = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
_DOCUMENT_ID = UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")


def _make_advocate_profile(
    *,
    user_id: UUID = _ADVOCATE_ID,
    verification_status: str = "verified",
) -> AdvocateProfileRecord:
    return AdvocateProfileRecord(
        user_id=user_id,
        full_name="Test Advocate",
        bar_council_id="BAR/KA/2024/00001",
        registration_number=None,
        photo_url=None,
        bio="Experienced in criminal law.",
        years_of_experience=8,
        languages=["en", "kn"],
        specializations=["criminal", "civil"],
        jurisdictions=[],
        education=[],
        notable_cases=None,
        consultation_fee_min_inr=1000,
        consultation_fee_max_inr=5000,
        availability={},
        contact_preferences={},
        verification_status=verification_status,
        verified_at=_FIXED_NOW if verification_status == "verified" else None,
        verified_by_user_id=None,
        rejection_reason=None,
        ratings_avg=0.0,
        ratings_count=0,
        created_at=_FIXED_NOW,
        updated_at=_FIXED_NOW,
    )


def _make_case_link() -> dict[str, object]:
    return {
        "id": "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee",
        "document_id": str(_DOCUMENT_ID),
        "advocate_user_id": str(_ADVOCATE_ID),
        "role": "counsel",
        "status": "claimed",
        "created_at": _FIXED_NOW.isoformat(),
        "verified_at": None,
        "verified_by_user_id": None,
        "document_title": "sample.pdf",
        "court_name": "High Court",
        "order_date": "2026-04-20",
        "advocate_full_name": "Test Advocate",
        "advocate_photo_url": None,
    }


# ---------------------------------------------------------------------------
# Public directory listing
# ---------------------------------------------------------------------------


def test_list_advocates_is_public_and_returns_200(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        user_persistence,
        "list_advocates",
        MagicMock(return_value=(0, [])),
    )
    resp = _client.get(_BASE)
    assert resp.status_code == 200
    assert resp.json()["data"]["total"] == 0
    assert resp.json()["data"]["items"] == []


def test_list_advocates_passes_filters_to_persistence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_list = MagicMock(return_value=(0, []))
    monkeypatch.setattr(user_persistence, "list_advocates", mock_list)

    _client.get(f"{_BASE}?specialization=criminal&language=hi&limit=10&offset=5")

    _, kwargs = mock_list.call_args
    assert kwargs["specialization"] == "criminal"
    assert kwargs["language"] == "hi"
    assert kwargs["limit"] == 10
    assert kwargs["offset"] == 5
    # Public endpoint must only request verified advocates.
    assert kwargs["only_verified"] is True


def test_list_advocates_rejects_invalid_specialization() -> None:
    resp = _client.get(f"{_BASE}?specialization=underwater_basket_weaving")
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Public profile detail
# ---------------------------------------------------------------------------


def test_get_verified_advocate_returns_200(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = _make_advocate_profile(verification_status="verified")
    monkeypatch.setattr(
        user_persistence,
        "get_advocate_profile",
        MagicMock(return_value=profile),
    )
    resp = _client.get(f"{_BASE}/{_ADVOCATE_ID}")
    assert resp.status_code == 200


def test_get_pending_advocate_returns_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pending advocates must not be visible in the public directory."""
    profile = _make_advocate_profile(verification_status="pending")
    monkeypatch.setattr(
        user_persistence,
        "get_advocate_profile",
        MagicMock(return_value=profile),
    )
    resp = _client.get(f"{_BASE}/{_ADVOCATE_ID}")
    assert resp.status_code == 404


def test_get_nonexistent_advocate_returns_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        user_persistence,
        "get_advocate_profile",
        MagicMock(return_value=None),
    )
    resp = _client.get(f"{_BASE}/{_ADVOCATE_ID}")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Pending verification queue
# ---------------------------------------------------------------------------


def test_pending_queue_accessible_to_judge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    judge = make_user(user_id=str(_JUDGE_ID), role="judge", status="active")
    monkeypatch.setattr(
        user_persistence, "get_user_by_id", MagicMock(return_value=judge)
    )
    monkeypatch.setattr(
        user_persistence,
        "list_advocates",
        MagicMock(return_value=(1, [_make_advocate_profile(verification_status="pending")])),
    )

    resp = _client.get(f"{_BASE}/pending", headers=bearer(judge))
    assert resp.status_code == 200
    assert resp.json()["data"]["total"] == 1


def test_pending_queue_forbidden_for_citizen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    citizen = make_user(role="citizen", status="active")
    monkeypatch.setattr(
        user_persistence, "get_user_by_id", MagicMock(return_value=citizen)
    )
    resp = _client.get(f"{_BASE}/pending", headers=bearer(citizen))
    assert resp.status_code == 403


def test_pending_queue_forbidden_for_advocate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    advocate = make_user(role="advocate", status="active")
    monkeypatch.setattr(
        user_persistence, "get_user_by_id", MagicMock(return_value=advocate)
    )
    resp = _client.get(f"{_BASE}/pending", headers=bearer(advocate))
    assert resp.status_code == 403


def test_pending_queue_passes_pending_only_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    judge = make_user(user_id=str(_JUDGE_ID), role="judge")
    mock_list = MagicMock(return_value=(0, []))
    monkeypatch.setattr(user_persistence, "get_user_by_id", MagicMock(return_value=judge))
    monkeypatch.setattr(user_persistence, "list_advocates", mock_list)

    _client.get(f"{_BASE}/pending", headers=bearer(judge))

    _, kwargs = mock_list.call_args
    assert kwargs.get("pending_only") is True
    assert kwargs.get("only_verified") is False


# ---------------------------------------------------------------------------
# Verify advocate
# ---------------------------------------------------------------------------


def test_verify_advocate_as_judge_returns_200(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    judge = make_user(user_id=str(_JUDGE_ID), role="judge")
    pending_profile = _make_advocate_profile(verification_status="pending")
    verified_profile = _make_advocate_profile(verification_status="verified")

    monkeypatch.setattr(user_persistence, "get_user_by_id", MagicMock(return_value=judge))
    monkeypatch.setattr(
        user_persistence, "get_advocate_profile", MagicMock(return_value=pending_profile)
    )
    monkeypatch.setattr(
        user_persistence, "set_advocate_verification", MagicMock(return_value=verified_profile)
    )

    resp = _client.post(f"{_BASE}/{_ADVOCATE_ID}/verify", headers=bearer(judge))
    assert resp.status_code == 200


def test_verify_advocate_as_citizen_returns_403(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    citizen = make_user(role="citizen")
    monkeypatch.setattr(user_persistence, "get_user_by_id", MagicMock(return_value=citizen))

    resp = _client.post(f"{_BASE}/{_ADVOCATE_ID}/verify", headers=bearer(citizen))
    assert resp.status_code == 403


def test_verify_nonexistent_advocate_returns_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    judge = make_user(user_id=str(_JUDGE_ID), role="judge")
    monkeypatch.setattr(user_persistence, "get_user_by_id", MagicMock(return_value=judge))
    monkeypatch.setattr(
        user_persistence, "get_advocate_profile", MagicMock(return_value=None)
    )

    resp = _client.post(f"{_BASE}/{_ADVOCATE_ID}/verify", headers=bearer(judge))
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Reject advocate
# ---------------------------------------------------------------------------


def test_reject_advocate_as_judge_returns_200(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    judge = make_user(user_id=str(_JUDGE_ID), role="judge")
    pending_profile = _make_advocate_profile(verification_status="pending")
    rejected_profile = _make_advocate_profile(verification_status="rejected")

    monkeypatch.setattr(user_persistence, "get_user_by_id", MagicMock(return_value=judge))
    monkeypatch.setattr(
        user_persistence, "get_advocate_profile", MagicMock(return_value=pending_profile)
    )
    monkeypatch.setattr(
        user_persistence, "set_advocate_verification", MagicMock(return_value=rejected_profile)
    )

    resp = _client.post(
        f"{_BASE}/{_ADVOCATE_ID}/reject",
        json={"reason": "Invalid bar council ID"},
        headers=bearer(judge),
    )
    assert resp.status_code == 200
    # Verify the rejection reason was forwarded.
    _, kwargs = user_persistence.set_advocate_verification.call_args
    assert kwargs["rejection_reason"] == "Invalid bar council ID"
    assert kwargs["status"] == "rejected"


def test_reject_advocate_as_citizen_returns_403(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    citizen = make_user(role="citizen")
    monkeypatch.setattr(user_persistence, "get_user_by_id", MagicMock(return_value=citizen))

    resp = _client.post(
        f"{_BASE}/{_ADVOCATE_ID}/reject",
        json={"reason": "No reason"},
        headers=bearer(citizen),
    )
    assert resp.status_code == 403


def test_list_advocate_cases_calls_persistence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_list = MagicMock(return_value=(0, []))
    monkeypatch.setattr(user_persistence, "list_advocate_cases", mock_list)
    resp = _client.get(f"{_BASE}/{_ADVOCATE_ID}/cases?status=verified&limit=10&offset=5")
    assert resp.status_code == 200
    _, kwargs = mock_list.call_args
    assert kwargs["status"] == "verified"
    assert kwargs["limit"] == 10
    assert kwargs["offset"] == 5


def test_claim_case_forbidden_for_non_advocate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    citizen = make_user(role="citizen", status="active")
    monkeypatch.setattr(user_persistence, "get_user_by_id", MagicMock(return_value=citizen))
    resp = _client.post(
        f"{_BASE}/me/cases",
        json={"document_id": str(_DOCUMENT_ID), "role": "counsel"},
        headers=bearer(citizen),
    )
    assert resp.status_code == 403


def test_claim_case_as_advocate_returns_200(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    advocate = make_user(user_id=str(_ADVOCATE_ID), role="advocate", status="active")
    monkeypatch.setattr(user_persistence, "get_user_by_id", MagicMock(return_value=advocate))
    monkeypatch.setattr(
        "orderflow_api.api.routes.advocates.get_document",
        MagicMock(return_value=object()),
    )
    monkeypatch.setattr(
        "orderflow_api.api.routes.advocates.get_persisted_document",
        MagicMock(return_value=None),
    )
    monkeypatch.setattr(
        user_persistence,
        "claim_advocate_case",
        MagicMock(return_value=type("CaseLink", (), {"model_dump": lambda self: _make_case_link()})()),
    )

    resp = _client.post(
        f"{_BASE}/me/cases",
        json={"document_id": str(_DOCUMENT_ID), "role": "counsel"},
        headers=bearer(advocate),
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["message"] == "advocate_case_claimed"
    assert payload["data"]["item"]["document_id"] == str(_DOCUMENT_ID)
