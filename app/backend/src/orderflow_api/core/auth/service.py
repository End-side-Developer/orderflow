from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from orderflow_api.api import user_persistence
from orderflow_api.core.auth.passwords import hash_password, verify_password
from orderflow_api.core.auth.tokens import (
    AccessTokenClaims,
    RefreshTokenClaims,
    issue_access_token,
    issue_refresh_token,
    refresh_token_expiry,
    refresh_token_issued_at,
)
from orderflow_api.core.config import settings
from orderflow_api.schemas.advocates import (
    AdvocateProfileBase,
    AdvocateProfileRecord,
)
from orderflow_api.schemas.users import UserRecord


class AuthError(Exception):
    """Generic authentication failure."""


class InvalidCredentials(AuthError):
    pass


class AccountNotActive(AuthError):
    def __init__(self, status: str) -> None:
        super().__init__(f"account status: {status}")
        self.status = status


@dataclass(frozen=True)
class IssuedTokens:
    access_token: str
    access_claims: AccessTokenClaims
    refresh_token: str
    refresh_claims: RefreshTokenClaims


def register_citizen_or_advocate(
    *,
    email: str,
    password: str,
    full_name: str,
    role: str,
    phone: str | None,
    preferred_language: str | None,
    advocate_profile: AdvocateProfileBase | None,
) -> tuple[UserRecord, AdvocateProfileRecord | None]:
    """
    Self-serve registration. Citizens land in `active`; advocates in
    `pending_verification` until a judge/government user verifies them.
    Judges/government accounts are not registerable through this path.
    """
    if role not in ("citizen", "advocate"):
        raise AuthError(f"role '{role}' is not self-registerable")

    status = "pending_verification" if role == "advocate" else "active"
    password_hash = hash_password(password)

    user = user_persistence.insert_user(
        email=email,
        password_hash=password_hash,
        role=role,
        status=status,
        full_name=full_name,
        phone=phone,
        preferred_language=preferred_language or "en",
    )

    advocate_record: AdvocateProfileRecord | None = None
    if role == "advocate" and advocate_profile is not None:
        try:
            user_persistence.insert_advocate_profile(
                user_id=user.id,
                bar_council_id=advocate_profile.bar_council_id,
                registration_number=advocate_profile.registration_number,
                photo_url=advocate_profile.photo_url,
                bio=advocate_profile.bio,
                years_of_experience=advocate_profile.years_of_experience,
                languages=advocate_profile.languages,
                specializations=advocate_profile.specializations,
                jurisdictions=[j.model_dump() for j in advocate_profile.jurisdictions],
                education=[e.model_dump() for e in advocate_profile.education],
                notable_cases=advocate_profile.notable_cases,
                consultation_fee_min_inr=advocate_profile.consultation_fee_min_inr,
                consultation_fee_max_inr=advocate_profile.consultation_fee_max_inr,
                availability=advocate_profile.availability.model_dump(),
                contact_preferences=advocate_profile.contact_preferences.model_dump(),
            )
        except user_persistence.BarCouncilIdAlreadyRegistered:
            # The user row was already inserted; surface as auth error so the
            # route can return 409 conflict. (A txn-spanning rollback would be
            # nicer; pragmatic for MVP.)
            raise
        advocate_record = user_persistence.get_advocate_profile(user.id)

    return user, advocate_record


def authenticate(*, email: str, password: str) -> tuple[UserRecord, str]:
    """Returns (user, password_hash) on success. Raises on failure."""
    found = user_persistence.get_user_by_email(email)
    if found is None:
        # Bcrypt verify a dummy hash to keep timing roughly constant —
        # avoids a trivial user-enumeration oracle.
        verify_password(password, "$2b$12$" + "a" * 53)
        raise InvalidCredentials("invalid email or password")

    user, stored_hash = found
    if not verify_password(password, stored_hash):
        raise InvalidCredentials("invalid email or password")

    if user.status not in ("active", "pending_verification"):
        # `pending_verification` advocates can still log in (so they can see
        # their pending banner & edit their profile); only suspended/disabled
        # accounts are blocked.
        raise AccountNotActive(user.status)

    return user, stored_hash


def issue_session(
    *,
    user: UserRecord,
    user_agent: str | None,
    ip_address: str | None,
) -> IssuedTokens:
    access_token, access_claims = issue_access_token(user_id=user.id, role=user.role)
    refresh_token, refresh_claims = issue_refresh_token(user_id=user.id)

    user_persistence.insert_refresh_token(
        token_id=refresh_claims.jti,
        user_id=user.id,
        issued_at=refresh_token_issued_at(refresh_claims),
        expires_at=refresh_token_expiry(refresh_claims),
        user_agent=user_agent,
        ip_address=ip_address,
    )
    user_persistence.update_user_last_login(user.id)

    return IssuedTokens(
        access_token=access_token,
        access_claims=access_claims,
        refresh_token=refresh_token,
        refresh_claims=refresh_claims,
    )


def rotate_refresh(
    *,
    incoming_claims: RefreshTokenClaims,
    user_agent: str | None,
    ip_address: str | None,
) -> IssuedTokens:
    """
    Rotate a refresh token. If the incoming token is already revoked we treat
    it as a reuse attempt and revoke the entire chain — standard refresh-token-
    rotation defense.
    """
    row = user_persistence.get_active_refresh_token(incoming_claims.jti)
    if row is None:
        raise InvalidCredentials("unknown refresh token")

    if row["revoked_at"] is not None:
        # Reuse detected.
        user_persistence.revoke_all_user_tokens(incoming_claims.sub)
        raise InvalidCredentials("refresh token reuse detected")

    if row["expires_at"] is not None and row["expires_at"] < datetime.now(UTC):
        raise InvalidCredentials("refresh token expired")

    user = user_persistence.get_user_by_id(incoming_claims.sub)
    if user is None or user.status not in ("active", "pending_verification"):
        raise InvalidCredentials("user no longer eligible")

    new_access, new_access_claims = issue_access_token(user_id=user.id, role=user.role)
    new_refresh, new_refresh_claims = issue_refresh_token(user_id=user.id)

    user_persistence.insert_refresh_token(
        token_id=new_refresh_claims.jti,
        user_id=user.id,
        issued_at=refresh_token_issued_at(new_refresh_claims),
        expires_at=refresh_token_expiry(new_refresh_claims),
        user_agent=user_agent,
        ip_address=ip_address,
    )
    user_persistence.revoke_refresh_token(
        incoming_claims.jti,
        replaced_by=new_refresh_claims.jti,
    )

    return IssuedTokens(
        access_token=new_access,
        access_claims=new_access_claims,
        refresh_token=new_refresh,
        refresh_claims=new_refresh_claims,
    )


def revoke_session(refresh_jti: UUID) -> None:
    user_persistence.revoke_refresh_token(refresh_jti)


def change_password(
    *,
    user_id: UUID,
    current_password: str,
    new_password: str,
) -> None:
    found = user_persistence.get_user_with_password_hash(user_id)
    if found is None:
        raise InvalidCredentials("user not found")
    _, stored_hash = found
    if not verify_password(current_password, stored_hash):
        raise InvalidCredentials("current password is incorrect")
    user_persistence.update_user_password(user_id, hash_password(new_password))
    # Invalidate every existing session — forces re-login on other devices.
    user_persistence.revoke_all_user_tokens(user_id)


def access_ttl_seconds() -> int:
    return settings.orderflow_access_ttl_seconds
