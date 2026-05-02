"""Shared test helpers loaded automatically by pytest for all tests."""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from orderflow_api.core.auth.service import IssuedTokens
from orderflow_api.core.auth.tokens import issue_access_token, issue_refresh_token
from orderflow_api.main import app
from orderflow_api.schemas.users import UserRecord

_FIXED_NOW = datetime(2026, 5, 2, 12, 0, 0, tzinfo=UTC)

# Sentinel no-op for persistence side-effects that don't affect assertions.
_NO_OP = lambda *a, **kw: None  # noqa: E731


def make_user(
    *,
    user_id: str = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    email: str = "test@example.com",
    role: str = "citizen",
    status: str = "active",
    full_name: str = "Test User",
) -> UserRecord:
    return UserRecord(
        id=UUID(user_id),
        email=email,
        role=role,
        status=status,
        full_name=full_name,
        phone=None,
        preferred_language="en",
        email_verified_at=None,
        last_login_at=None,
        profile_metadata={},
        created_at=_FIXED_NOW,
        updated_at=_FIXED_NOW,
    )


def make_issued_tokens(user: UserRecord) -> IssuedTokens:
    """Create real (signed) access + refresh tokens for a given user."""
    access_token, access_claims = issue_access_token(user_id=user.id, role=user.role)
    refresh_token, refresh_claims = issue_refresh_token(user_id=user.id)
    return IssuedTokens(
        access_token=access_token,
        access_claims=access_claims,
        refresh_token=refresh_token,
        refresh_claims=refresh_claims,
    )


def bearer(user: UserRecord) -> dict[str, str]:
    """Returns an Authorization header dict for use with TestClient."""
    access_token, _ = issue_access_token(user_id=user.id, role=user.role)
    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture
def http() -> TestClient:
    """Fresh TestClient for each test."""
    return TestClient(app)
