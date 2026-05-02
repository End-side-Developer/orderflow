from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status

from orderflow_api.api import user_persistence
from orderflow_api.api.dependencies.auth import get_current_user
from orderflow_api.api.response import success
from orderflow_api.core.auth.permissions import Role
from orderflow_api.schemas.users import (
    UserEnvelope,
    UserUpdateRequest,
)


router = APIRouter(prefix="/users", tags=["users"])


_PRIVILEGED_ROLES = {Role.JUDGE.value, Role.GOVERNMENT.value}


@router.get("/{user_id}", response_model=UserEnvelope)
async def get_user_route(
    request: Request,
    user_id: UUID,
    caller=Depends(get_current_user),
) -> dict[str, object]:
    request_id = getattr(request.state, "request_id", None)

    if caller.id != user_id and caller.role not in _PRIVILEGED_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "forbidden", "message": "not allowed for this user"},
        )

    target = user_persistence.get_user_by_id(user_id)
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "user_not_found", "message": "user not found"},
        )
    return success(data=target, request_id=request_id)


@router.patch("/{user_id}", response_model=UserEnvelope)
async def update_user_route(
    request: Request,
    user_id: UUID,
    payload: UserUpdateRequest,
    caller=Depends(get_current_user),
) -> dict[str, object]:
    request_id = getattr(request.state, "request_id", None)

    is_self = caller.id == user_id
    is_privileged = caller.role in _PRIVILEGED_ROLES
    is_government = caller.role == Role.GOVERNMENT.value

    if not (is_self or is_privileged):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "forbidden", "message": "not allowed for this user"},
        )

    # Privilege gates: status changes require judge/gov; role changes require gov.
    if payload.status is not None and not is_privileged:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "forbidden",
                "message": "status changes require judge/government role",
            },
        )
    if payload.role is not None and not is_government:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "forbidden",
                "message": "role changes require government role",
            },
        )

    updated = user_persistence.update_user_fields(
        user_id,
        full_name=payload.full_name,
        phone=payload.phone,
        preferred_language=payload.preferred_language,
        profile_metadata=payload.profile_metadata,
        role=payload.role,
        status=payload.status,
    )
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "user_not_found", "message": "user not found"},
        )
    return success(data=updated, request_id=request_id, message="user_updated")
