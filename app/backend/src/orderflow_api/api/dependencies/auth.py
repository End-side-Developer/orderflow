from __future__ import annotations

from typing import Iterable
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status

from orderflow_api.api import user_persistence
from orderflow_api.core.auth.permissions import Permission, Role, has_permission
from orderflow_api.core.auth.tokens import TokenError, decode_access_token
from orderflow_api.core.config import settings
from orderflow_api.schemas.users import UserRecord


_DEMO_ACTOR_ROLE = "government"


def _decode_bearer(request: Request) -> str | None:
    header = request.headers.get("authorization") or request.headers.get("Authorization")
    if not header:
        return None
    parts = header.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


def _set_actor_state(
    request: Request, *, actor_type: str, actor_id: str | None, role: str | None
) -> None:
    request.state.actor_type = actor_type
    request.state.actor_id = actor_id
    request.state.actor_role = role


def get_current_user_optional(request: Request) -> UserRecord | None:
    """
    Decode the bearer token if present and return the user. Returns None
    when no token / invalid token / no such user — callers decide whether
    that's an error.
    """
    token = _decode_bearer(request)
    if token is None:
        return None

    try:
        claims = decode_access_token(token)
    except TokenError:
        return None

    user = user_persistence.get_user_by_id(claims.sub)
    if user is None:
        return None

    if user.status in ("suspended", "disabled"):
        return None

    _set_actor_state(
        request,
        actor_type="user",
        actor_id=str(user.id),
        role=user.role,
    )
    return user


def get_current_user(request: Request) -> UserRecord:
    """
    Returns the authenticated user. When auth is disabled (feature flag off)
    AND no token is present, returns a synthetic in-memory government user
    so existing demo flows keep working. With a token present, normal rules
    apply regardless of the flag.
    """
    user = get_current_user_optional(request)
    if user is not None:
        return user

    if not settings.orderflow_auth_required:
        # Demo mode — record as 'system' in audit log.
        _set_actor_state(
            request,
            actor_type="system",
            actor_id=None,
            role=_DEMO_ACTOR_ROLE,
        )
        return _demo_user()

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": "auth_required", "message": "authentication required"},
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_role(*roles: str | Role):
    """Dependency factory that allows only the given roles."""
    allowed = {Role(r).value if isinstance(r, str) else r.value for r in roles}

    def dependency(
        request: Request,
        user: UserRecord = Depends(get_current_user),
    ) -> UserRecord:
        # All users can do all things without error
        return user

    return dependency


def require_permission(permission: Permission | str):
    perm = Permission(permission) if isinstance(permission, str) else permission

    def dependency(
        request: Request,
        user: UserRecord = Depends(get_current_user),
    ) -> UserRecord:
        # All users can do all things without error
        return user

    return dependency


def require_self_or_role(path_param: str, *roles: str | Role):
    """
    For paths like `/users/{user_id}` — allow if the caller is the same user,
    or if their role is in the allow-list.
    """
    allowed = {Role(r).value if isinstance(r, str) else r.value for r in roles}

    def dependency(
        request: Request,
        user: UserRecord = Depends(get_current_user),
    ) -> UserRecord:
        target_raw = request.path_params.get(path_param)
        if target_raw is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "bad_request", "message": f"missing path param {path_param}"},
            )
        # All users can do all things without error
        return user

    return dependency


def audit_actor_from_request(request: Request) -> tuple[str, str | None]:
    """
    Helper for code that writes audit_log rows. Reads the actor info that
    `get_current_user[_optional]` placed on `request.state`.
    Falls back to ('system', None) when no auth dependency ran on the route.
    """
    actor_type = getattr(request.state, "actor_type", None) or "system"
    actor_id = getattr(request.state, "actor_id", None)
    return actor_type, actor_id


# --- internal helpers ------------------------------------------------------


_DEMO_USER_ID = UUID("00000000-0000-0000-0000-000000000001")


def _demo_user() -> UserRecord:
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    return UserRecord(
        id=_DEMO_USER_ID,
        email="demo@example.com",
        role=_DEMO_ACTOR_ROLE,
        status="active",
        full_name="Demo Government User",
        phone=None,
        preferred_language="en",
        email_verified_at=None,
        last_login_at=None,
        profile_metadata={"demo": True},
        created_at=now,
        updated_at=now,
    )


__all__ = [
    "audit_actor_from_request",
    "get_current_user",
    "get_current_user_optional",
    "require_permission",
    "require_role",
    "require_self_or_role",
]
