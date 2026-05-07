"""Tests for /auth/* endpoints.

All persistence and service calls are monkeypatched so no real DB is needed.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

import orderflow_api.api.user_persistence as user_persistence
import orderflow_api.core.auth.service as auth_service
from orderflow_api.core.config import settings
from orderflow_api.main import app
from tests.conftest import make_issued_tokens, make_user

_BASE = "/api/v1/auth"
_client = TestClient(app)

# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------


def test_register_citizen_returns_201_with_active_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = make_user(role="citizen", status="active")
    monkeypatch.setattr(
        auth_service,
        "register_citizen_or_advocate",
        MagicMock(return_value=(user, None)),
    )
    resp = _client.post(
        f"{_BASE}/register",
        json={
            "email": "citizen@test.com",
            "password": "Password123!",
            "full_name": "Test Citizen",
            "role": "citizen",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["data"]["user"]["role"] == "citizen"
    assert body["data"]["user"]["status"] == "active"


def test_register_advocate_returns_201_with_pending_verification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = make_user(role="advocate", status="pending_verification")
    monkeypatch.setattr(
        auth_service,
        "register_citizen_or_advocate",
        MagicMock(return_value=(user, None)),
    )
    resp = _client.post(
        f"{_BASE}/register",
        json={
            "email": "adv@test.com",
            "password": "Password123!",
            "full_name": "Test Advocate",
            "role": "advocate",
            "advocate_profile": {"bar_council_id": "BAR/KA/2024/00001"},
        },
    )
    assert resp.status_code == 201
    assert resp.json()["data"]["user"]["status"] == "pending_verification"


def test_register_judge_role_is_forbidden() -> None:
    """Judge/government self-registration must be blocked at the route level."""
    resp = _client.post(
        f"{_BASE}/register",
        json={
            "email": "judge@test.com",
            "password": "Password123!",
            "full_name": "Judge",
            "role": "judge",
        },
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "self_registration_not_allowed"


def test_register_duplicate_email_returns_409(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        auth_service,
        "register_citizen_or_advocate",
        MagicMock(side_effect=user_persistence.EmailAlreadyRegistered("taken")),
    )
    resp = _client.post(
        f"{_BASE}/register",
        json={
            "email": "dup@test.com",
            "password": "Password123!",
            "full_name": "Dup",
            "role": "citizen",
        },
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "email_taken"


def test_register_duplicate_bar_council_id_returns_409(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        auth_service,
        "register_citizen_or_advocate",
        MagicMock(side_effect=user_persistence.BarCouncilIdAlreadyRegistered("taken")),
    )
    resp = _client.post(
        f"{_BASE}/register",
        json={
            "email": "adv2@test.com",
            "password": "Password123!",
            "full_name": "Adv2",
            "role": "advocate",
            "advocate_profile": {"bar_council_id": "BAR/KA/2024/00002"},
        },
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "bar_council_id_taken"


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


def test_login_wrong_password_returns_401(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        auth_service,
        "authenticate",
        MagicMock(side_effect=auth_service.InvalidCredentials("bad password")),
    )
    monkeypatch.setattr(user_persistence, "record_credentials_event", MagicMock())

    resp = _client.post(
        f"{_BASE}/login",
        json={"email": "user@test.com", "password": "wrong"},
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "invalid_credentials"


def test_login_suspended_account_returns_403(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        auth_service,
        "authenticate",
        MagicMock(side_effect=auth_service.AccountNotActive("suspended")),
    )

    resp = _client.post(
        f"{_BASE}/login",
        json={"email": "suspended@test.com", "password": "Pass123!"},
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "account_not_active"


def test_login_success_returns_access_token_and_sets_cookie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = make_user(role="judge", status="active")
    issued = make_issued_tokens(user)

    monkeypatch.setattr(auth_service, "authenticate", MagicMock(return_value=(user, "hash")))
    monkeypatch.setattr(auth_service, "issue_session", MagicMock(return_value=issued))
    monkeypatch.setattr(user_persistence, "record_credentials_event", MagicMock())
    monkeypatch.setattr(user_persistence, "get_advocate_profile", MagicMock(return_value=None))

    resp = _client.post(
        f"{_BASE}/login",
        json={"email": "judge@test.com", "password": "Pass123!"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "access_token" in data
    assert data["user"]["role"] == "judge"
    assert settings.orderflow_refresh_cookie_name in resp.cookies
    assert "Path=/" in resp.headers["set-cookie"]


def test_login_for_advocate_attaches_advocate_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = make_user(role="advocate", status="pending_verification")
    issued = make_issued_tokens(user)

    monkeypatch.setattr(auth_service, "authenticate", MagicMock(return_value=(user, "hash")))
    monkeypatch.setattr(auth_service, "issue_session", MagicMock(return_value=issued))
    monkeypatch.setattr(user_persistence, "record_credentials_event", MagicMock())
    # Return None — we only care that the function was called, not what it returns.
    monkeypatch.setattr(user_persistence, "get_advocate_profile", MagicMock(return_value=None))

    resp = _client.post(
        f"{_BASE}/login",
        json={"email": "adv@test.com", "password": "Pass123!"},
    )
    assert resp.status_code == 200
    user_persistence.get_advocate_profile.assert_called_once_with(user.id)


# ---------------------------------------------------------------------------
# /auth/me
# ---------------------------------------------------------------------------


def test_me_returns_current_user_when_bearer_is_valid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = make_user(role="judge", email="judge@test.com")
    monkeypatch.setattr(user_persistence, "get_user_by_id", MagicMock(return_value=user))
    monkeypatch.setattr(user_persistence, "get_advocate_profile", MagicMock(return_value=None))

    from orderflow_api.core.auth.tokens import issue_access_token

    token, _ = issue_access_token(user_id=user.id, role=user.role)
    resp = _client.get(f"{_BASE}/me", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200
    assert resp.json()["data"]["user"]["email"] == "judge@test.com"


def test_me_with_no_bearer_in_demo_mode_returns_demo_user() -> None:
    """When ORDERFLOW_AUTH_REQUIRED=False (default), /auth/me returns demo actor."""
    resp = _client.get(f"{_BASE}/me")
    assert resp.status_code == 200
    assert resp.json()["data"]["user"]["role"] == "government"


def test_me_with_no_bearer_when_auth_required_returns_401(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "orderflow_auth_required", True)
    resp = _client.get(f"{_BASE}/me")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "auth_required"


# ---------------------------------------------------------------------------
# /auth/refresh
# ---------------------------------------------------------------------------


def test_refresh_without_cookie_returns_401() -> None:
    resp = TestClient(app).post(f"{_BASE}/refresh")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "no_refresh_token"


def test_refresh_with_valid_cookie_returns_new_access_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = make_user(role="citizen")
    issued = make_issued_tokens(user)

    monkeypatch.setattr(auth_service, "rotate_refresh", MagicMock(return_value=issued))
    monkeypatch.setattr(user_persistence, "record_credentials_event", MagicMock())
    monkeypatch.setattr(user_persistence, "get_user_by_id", MagicMock(return_value=user))

    refresh_cookie = {settings.orderflow_refresh_cookie_name: issued.refresh_token}
    resp = _client.post(f"{_BASE}/refresh", cookies=refresh_cookie)

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "access_token" in data
    assert data["user"]["role"] == "citizen"


def test_refresh_with_invalid_token_returns_401() -> None:
    bad_token = "not.a.real.token"
    refresh_cookie = {settings.orderflow_refresh_cookie_name: bad_token}
    resp = _client.post(f"{_BASE}/refresh", cookies=refresh_cookie)
    assert resp.status_code == 401


def test_refresh_token_reuse_returns_401(monkeypatch: pytest.MonkeyPatch) -> None:
    user = make_user(role="citizen")
    issued = make_issued_tokens(user)

    monkeypatch.setattr(
        auth_service,
        "rotate_refresh",
        MagicMock(side_effect=auth_service.InvalidCredentials("reuse detected")),
    )

    refresh_cookie = {settings.orderflow_refresh_cookie_name: issued.refresh_token}
    resp = _client.post(f"{_BASE}/refresh", cookies=refresh_cookie)
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "refresh_failed"


# ---------------------------------------------------------------------------
# /auth/logout
# ---------------------------------------------------------------------------


def test_logout_returns_200_and_clears_cookie(monkeypatch: pytest.MonkeyPatch) -> None:
    user = make_user()
    issued = make_issued_tokens(user)

    monkeypatch.setattr(auth_service, "revoke_session", MagicMock())
    monkeypatch.setattr(user_persistence, "record_credentials_event", MagicMock())

    refresh_cookie = {settings.orderflow_refresh_cookie_name: issued.refresh_token}
    resp = _client.post(f"{_BASE}/logout", cookies=refresh_cookie)

    assert resp.status_code == 200
    assert resp.json()["data"]["logged_out"] is True
    cookie_name = settings.orderflow_refresh_cookie_name
    assert cookie_name in resp.headers.get("set-cookie", "")


def test_logout_without_cookie_still_returns_200() -> None:
    """Logout should be idempotent — no cookie is not an error."""
    resp = _client.post(f"{_BASE}/logout")
    assert resp.status_code == 200
    assert resp.json()["data"]["logged_out"] is True
