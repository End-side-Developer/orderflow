from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from orderflow_api.api import user_persistence
from orderflow_api.api.dependencies.auth import (
    require_permission,
)
from orderflow_api.api.response import success
from orderflow_api.core.auth.permissions import Permission, Role
from orderflow_api.api.document_persistence import get_persisted_document
from orderflow_api.api.stub_repository import get_document
from orderflow_api.schemas.advocates import (
    ADVOCATE_SPECIALIZATIONS,
    AdvocateCaseClaimRequest,
    AdvocateCaseLinkEnvelope,
    AdvocateCaseLinksData,
    AdvocateCaseLinksEnvelope,
    AdvocateDirectoryEnvelope,
    AdvocateProfileEnvelope,
    AdvocateProfileUpdateRequest,
    AdvocateRejectRequest,
)


router = APIRouter(prefix="/advocates", tags=["advocates"])


@router.get("", response_model=AdvocateDirectoryEnvelope)
async def list_advocates_route(
    request: Request,
    q: str | None = Query(default=None, max_length=200),
    specialization: str | None = Query(default=None),
    jurisdiction_level: str | None = Query(default=None),
    jurisdiction_state: str | None = Query(default=None),
    language: str | None = Query(default=None, max_length=8),
    min_experience: int | None = Query(default=None, ge=0, le=80),
    max_fee: int | None = Query(default=None, ge=0),
    sort: str = Query(default="rating", pattern="^(rating|experience|recent)$"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    request_id = getattr(request.state, "request_id", None)

    if specialization is not None and specialization not in ADVOCATE_SPECIALIZATIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "invalid_specialization",
                "message": f"specialization must be one of {list(ADVOCATE_SPECIALIZATIONS)}",
            },
        )

    total, items = user_persistence.list_advocates(
        q=q,
        specialization=specialization,
        jurisdiction_level=jurisdiction_level,
        jurisdiction_state=jurisdiction_state,
        language=language,
        min_experience=min_experience,
        max_fee=max_fee,
        sort=sort,
        only_verified=True,
        limit=limit,
        offset=offset,
    )

    return success(
        data={
            "total": total,
            "limit": limit,
            "offset": offset,
            "items": items,
        },
        request_id=request_id,
    )


@router.get("/pending", response_model=AdvocateDirectoryEnvelope)
async def list_pending_advocates_route(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _caller=Depends(require_permission(Permission.ADVOCATE_VERIFY)),
) -> dict[str, object]:
    """Pending-verification queue. Judge/government only."""
    request_id = getattr(request.state, "request_id", None)
    total, items = user_persistence.list_advocates(
        only_verified=False,
        pending_only=True,
        limit=limit,
        offset=offset,
    )
    return success(
        data={"total": total, "limit": limit, "offset": offset, "items": items},
        request_id=request_id,
    )


@router.get("/{user_id}", response_model=AdvocateProfileEnvelope)
async def get_advocate_route(
    request: Request,
    user_id: UUID,
) -> dict[str, object]:
    """Public profile view — only verified advocates are visible."""
    request_id = getattr(request.state, "request_id", None)
    profile = user_persistence.get_advocate_profile(user_id)
    if profile is None or profile.verification_status != "verified":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "advocate_not_found", "message": "advocate not found"},
        )
    return success(data=profile, request_id=request_id)


@router.patch(
    "/me",
    response_model=AdvocateProfileEnvelope,
)
async def update_advocate_me_route(
    request: Request,
    payload: AdvocateProfileUpdateRequest,
    user=Depends(require_permission(Permission.ADVOCATE_SELF_PROFILE_WRITE)),
) -> dict[str, object]:
    request_id = getattr(request.state, "request_id", None)
    if user.role != Role.ADVOCATE.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "forbidden",
                "message": "only advocate accounts may edit advocate profiles",
            },
        )

    updated = user_persistence.update_advocate_profile(
        user.id,
        photo_url=payload.photo_url,
        bio=payload.bio,
        years_of_experience=payload.years_of_experience,
        languages=payload.languages,
        specializations=payload.specializations,
        jurisdictions=(
            [j.model_dump() for j in payload.jurisdictions]
            if payload.jurisdictions is not None
            else None
        ),
        education=(
            [e.model_dump() for e in payload.education] if payload.education is not None else None
        ),
        notable_cases=payload.notable_cases,
        consultation_fee_min_inr=payload.consultation_fee_min_inr,
        consultation_fee_max_inr=payload.consultation_fee_max_inr,
        availability=payload.availability.model_dump() if payload.availability else None,
        contact_preferences=(
            payload.contact_preferences.model_dump() if payload.contact_preferences else None
        ),
        registration_number=payload.registration_number,
    )
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "advocate_not_found", "message": "advocate profile not found"},
        )
    return success(data=updated, request_id=request_id, message="advocate_profile_updated")


@router.get("/{user_id}/cases", response_model=AdvocateCaseLinksEnvelope)
async def list_advocate_cases_route(
    request: Request,
    user_id: UUID,
    status_filter: str | None = Query(default=None, alias="status", pattern="^(claimed|verified)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _caller=Depends(require_permission(Permission.CASE_READ)),
) -> dict[str, object]:
    request_id = getattr(request.state, "request_id", None)
    total, items = user_persistence.list_advocate_cases(
        user_id,
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    return success(
        data=AdvocateCaseLinksData(total=total, items=items).model_dump(),
        request_id=request_id,
    )


@router.post("/me/cases", response_model=AdvocateCaseLinkEnvelope)
async def claim_advocate_case_route(
    request: Request,
    payload: AdvocateCaseClaimRequest,
    user=Depends(require_permission(Permission.ADVOCATE_SELF_PROFILE_WRITE)),
) -> dict[str, object]:
    request_id = getattr(request.state, "request_id", None)
    if user.role != Role.ADVOCATE.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "forbidden",
                "message": "only advocate accounts may claim cases",
            },
        )

    document = get_document(payload.document_id) or get_persisted_document(payload.document_id)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "document_not_found", "message": "document not found"},
        )

    link = user_persistence.claim_advocate_case(
        advocate_user_id=user.id,
        document_id=payload.document_id,
        role=payload.role,
    )
    return success(
        data={"item": link.model_dump()},
        request_id=request_id,
        message="advocate_case_claimed",
    )


@router.delete("/me/cases/{document_id}")
async def unclaim_advocate_case_route(
    request: Request,
    document_id: UUID,
    user=Depends(require_permission(Permission.ADVOCATE_SELF_PROFILE_WRITE)),
) -> dict[str, object]:
    request_id = getattr(request.state, "request_id", None)
    if user.role != Role.ADVOCATE.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "forbidden",
                "message": "only advocate accounts may unclaim cases",
            },
        )

    deleted = user_persistence.unclaim_advocate_case(
        advocate_user_id=user.id,
        document_id=document_id,
    )
    return success(
        data={"deleted": deleted},
        request_id=request_id,
        message="advocate_case_unclaimed",
    )


@router.post("/{user_id}/cases/{document_id}/verify", response_model=AdvocateCaseLinkEnvelope)
async def verify_advocate_case_route(
    request: Request,
    user_id: UUID,
    document_id: UUID,
    caller=Depends(require_permission(Permission.ADVOCATE_VERIFY)),
) -> dict[str, object]:
    request_id = getattr(request.state, "request_id", None)
    link = user_persistence.verify_advocate_case(
        advocate_user_id=user_id,
        document_id=document_id,
        verified_by_user_id=caller.id,
    )
    if link is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "case_link_not_found", "message": "case link not found"},
        )
    return success(
        data={"item": link.model_dump()},
        request_id=request_id,
        message="advocate_case_verified",
    )


@router.post("/{user_id}/verify", response_model=AdvocateProfileEnvelope)
async def verify_advocate_route(
    request: Request,
    user_id: UUID,
    caller=Depends(require_permission(Permission.ADVOCATE_VERIFY)),
) -> dict[str, object]:
    request_id = getattr(request.state, "request_id", None)

    profile = user_persistence.get_advocate_profile(user_id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "advocate_not_found", "message": "advocate profile not found"},
        )

    updated = user_persistence.set_advocate_verification(
        user_id,
        status="verified",
        verified_by_user_id=caller.id,
        rejection_reason=None,
    )
    return success(data=updated, request_id=request_id, message="advocate_verified")


@router.post("/{user_id}/reject", response_model=AdvocateProfileEnvelope)
async def reject_advocate_route(
    request: Request,
    user_id: UUID,
    payload: AdvocateRejectRequest,
    caller=Depends(require_permission(Permission.ADVOCATE_VERIFY)),
) -> dict[str, object]:
    request_id = getattr(request.state, "request_id", None)

    profile = user_persistence.get_advocate_profile(user_id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "advocate_not_found", "message": "advocate profile not found"},
        )

    updated = user_persistence.set_advocate_verification(
        user_id,
        status="rejected",
        verified_by_user_id=caller.id,
        rejection_reason=payload.reason,
    )
    return success(data=updated, request_id=request_id, message="advocate_rejected")
