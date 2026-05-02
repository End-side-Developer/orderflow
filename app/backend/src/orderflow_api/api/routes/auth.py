from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from orderflow_api.api import user_persistence
from orderflow_api.api.dependencies.auth import get_current_user
from orderflow_api.api.response import success
from orderflow_api.core.auth import service as auth_service
from orderflow_api.core.auth.tokens import TokenError, decode_refresh_token
from orderflow_api.core.config import settings
from orderflow_api.schemas.auth import (
    LoginEnvelope,
    LoginRequest,
    MeEnvelope,
    PasswordChangeRequest,
    RefreshEnvelope,
    RegisterEnvelope,
    RegisterRequest,
)
from orderflow_api.schemas.users import UserRecord


router = APIRouter(prefix="/auth", tags=["auth"])


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip() or None
    return request.client.host if request.client else None


def _user_agent(request: Request) -> str | None:
    return request.headers.get("user-agent")


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.orderflow_refresh_cookie_name,
        value=token,
        max_age=settings.orderflow_refresh_ttl_seconds,
        httponly=True,
        secure=settings.orderflow_refresh_cookie_secure,
        samesite=settings.orderflow_refresh_cookie_samesite,
        domain=settings.orderflow_refresh_cookie_domain,
        path=settings.orderflow_refresh_cookie_path,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.orderflow_refresh_cookie_name,
        domain=settings.orderflow_refresh_cookie_domain,
        path=settings.orderflow_refresh_cookie_path,
    )


@router.post(
    "/register",
    response_model=RegisterEnvelope,
    status_code=status.HTTP_201_CREATED,
)
async def register_route(
    request: Request,
    payload: RegisterRequest,
) -> dict[str, object]:
    request_id = getattr(request.state, "request_id", None)

    if payload.role not in ("citizen", "advocate"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "self_registration_not_allowed",
                "message": (
                    "Judge and government accounts must be created by a "
                    "government administrator, not via public registration."
                ),
            },
        )

    try:
        user, advocate = auth_service.register_citizen_or_advocate(
            email=payload.email,
            password=payload.password,
            full_name=payload.full_name,
            role=payload.role,
            phone=payload.phone,
            preferred_language=payload.preferred_language,
            advocate_profile=payload.advocate_profile,
        )
    except user_persistence.EmailAlreadyRegistered as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "email_taken", "message": "email already registered"},
        ) from exc
    except user_persistence.BarCouncilIdAlreadyRegistered as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "bar_council_id_taken",
                "message": "bar council ID already registered",
            },
        ) from exc

    return success(
        data={"user": user, "advocate_profile": advocate},
        request_id=request_id,
        message="user_registered",
    )


@router.post("/login", response_model=LoginEnvelope)
async def login_route(
    request: Request,
    response: Response,
    payload: LoginRequest,
) -> dict[str, object]:
    request_id = getattr(request.state, "request_id", None)
    ip = _client_ip(request)
    ua = _user_agent(request)

    try:
        user, _ = auth_service.authenticate(
            email=payload.email,
            password=payload.password,
        )
    except auth_service.InvalidCredentials as exc:
        user_persistence.record_credentials_event(
            user_id=None,
            event="login_failed",
            ip_address=ip,
            user_agent=ua,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_credentials", "message": "invalid email or password"},
        ) from exc
    except auth_service.AccountNotActive as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "account_not_active",
                "message": f"account is {exc.status}",
            },
        ) from exc

    issued = auth_service.issue_session(user=user, user_agent=ua, ip_address=ip)
    user_persistence.record_credentials_event(
        user_id=user.id, event="login_success", ip_address=ip, user_agent=ua
    )
    _set_refresh_cookie(response, issued.refresh_token)

    advocate_profile = (
        user_persistence.get_advocate_profile(user.id) if user.role == "advocate" else None
    )

    return success(
        data={
            "access_token": issued.access_token,
            "token_type": "bearer",
            "expires_in": auth_service.access_ttl_seconds(),
            "user": user,
            "advocate_profile": advocate_profile,
        },
        request_id=request_id,
        message="logged_in",
    )


@router.post("/refresh", response_model=RefreshEnvelope)
async def refresh_route(
    request: Request,
    response: Response,
) -> dict[str, object]:
    request_id = getattr(request.state, "request_id", None)
    cookie_token = request.cookies.get(settings.orderflow_refresh_cookie_name)
    if not cookie_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "no_refresh_token", "message": "missing refresh token"},
        )

    try:
        claims = decode_refresh_token(cookie_token)
    except TokenError as exc:
        _clear_refresh_cookie(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_refresh_token", "message": "refresh token invalid"},
        ) from exc

    try:
        issued = auth_service.rotate_refresh(
            incoming_claims=claims,
            user_agent=_user_agent(request),
            ip_address=_client_ip(request),
        )
    except auth_service.InvalidCredentials as exc:
        _clear_refresh_cookie(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "refresh_failed", "message": str(exc)},
        ) from exc

    user_persistence.record_credentials_event(
        user_id=claims.sub,
        event="token_refreshed",
        ip_address=_client_ip(request),
        user_agent=_user_agent(request),
    )
    _set_refresh_cookie(response, issued.refresh_token)

    return success(
        data={
            "access_token": issued.access_token,
            "token_type": "bearer",
            "expires_in": auth_service.access_ttl_seconds(),
        },
        request_id=request_id,
        message="token_refreshed",
    )


@router.post("/logout")
async def logout_route(
    request: Request,
    response: Response,
) -> dict[str, object]:
    request_id = getattr(request.state, "request_id", None)
    cookie_token = request.cookies.get(settings.orderflow_refresh_cookie_name)
    if cookie_token:
        try:
            claims = decode_refresh_token(cookie_token)
            auth_service.revoke_session(claims.jti)
            user_persistence.record_credentials_event(
                user_id=claims.sub,
                event="logout",
                ip_address=_client_ip(request),
                user_agent=_user_agent(request),
            )
        except TokenError:
            pass
    _clear_refresh_cookie(response)
    return success(data={"logged_out": True}, request_id=request_id, message="logged_out")


@router.get("/me", response_model=MeEnvelope)
async def me_route(
    request: Request,
    user: UserRecord = Depends(get_current_user),
) -> dict[str, object]:
    request_id = getattr(request.state, "request_id", None)
    advocate_profile = (
        user_persistence.get_advocate_profile(user.id) if user.role == "advocate" else None
    )
    return success(
        data={"user": user, "advocate_profile": advocate_profile},
        request_id=request_id,
    )


@router.post("/password")
async def change_password_route(
    request: Request,
    payload: PasswordChangeRequest,
    user: UserRecord = Depends(get_current_user),
) -> dict[str, object]:
    request_id = getattr(request.state, "request_id", None)
    try:
        auth_service.change_password(
            user_id=user.id,
            current_password=payload.current_password,
            new_password=payload.new_password,
        )
    except auth_service.InvalidCredentials as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_credentials", "message": str(exc)},
        ) from exc

    user_persistence.record_credentials_event(
        user_id=user.id,
        event="password_changed",
        ip_address=_client_ip(request),
        user_agent=_user_agent(request),
    )
    return success(
        data={"changed": True},
        request_id=request_id,
        message="password_changed",
    )
