from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt

from orderflow_api.core.config import settings


class TokenError(Exception):
    """Raised when a JWT cannot be decoded or is otherwise invalid."""


@dataclass(frozen=True)
class AccessTokenClaims:
    sub: UUID
    role: str
    iat: int
    exp: int
    iss: str

    def to_dict(self) -> dict[str, object]:
        return {
            "sub": str(self.sub),
            "role": self.role,
            "iat": self.iat,
            "exp": self.exp,
            "iss": self.iss,
            "typ": "access",
        }


@dataclass(frozen=True)
class RefreshTokenClaims:
    sub: UUID
    jti: UUID
    iat: int
    exp: int
    iss: str

    def to_dict(self) -> dict[str, object]:
        return {
            "sub": str(self.sub),
            "jti": str(self.jti),
            "iat": self.iat,
            "exp": self.exp,
            "iss": self.iss,
            "typ": "refresh",
        }


def _now_ts() -> int:
    return int(datetime.now(tz=UTC).timestamp())


def issue_access_token(*, user_id: UUID, role: str) -> tuple[str, AccessTokenClaims]:
    iat = _now_ts()
    exp = iat + settings.orderflow_access_ttl_seconds
    claims = AccessTokenClaims(
        sub=user_id,
        role=role,
        iat=iat,
        exp=exp,
        iss=settings.orderflow_jwt_issuer,
    )
    token = jwt.encode(
        claims.to_dict(),
        settings.orderflow_jwt_secret,
        algorithm=settings.orderflow_jwt_alg,
    )
    return token, claims


def issue_refresh_token(
    *,
    user_id: UUID,
    jti: UUID | None = None,
) -> tuple[str, RefreshTokenClaims]:
    iat = _now_ts()
    exp = iat + settings.orderflow_refresh_ttl_seconds
    claims = RefreshTokenClaims(
        sub=user_id,
        jti=jti or uuid4(),
        iat=iat,
        exp=exp,
        iss=settings.orderflow_jwt_issuer,
    )
    token = jwt.encode(
        claims.to_dict(),
        settings.orderflow_jwt_secret,
        algorithm=settings.orderflow_jwt_alg,
    )
    return token, claims


def decode_access_token(token: str) -> AccessTokenClaims:
    payload = _decode(token, expected_typ="access")
    try:
        return AccessTokenClaims(
            sub=UUID(str(payload["sub"])),
            role=str(payload["role"]),
            iat=int(payload["iat"]),
            exp=int(payload["exp"]),
            iss=str(payload["iss"]),
        )
    except (KeyError, ValueError) as exc:
        raise TokenError("malformed access token") from exc


def decode_refresh_token(token: str) -> RefreshTokenClaims:
    payload = _decode(token, expected_typ="refresh")
    try:
        return RefreshTokenClaims(
            sub=UUID(str(payload["sub"])),
            jti=UUID(str(payload["jti"])),
            iat=int(payload["iat"]),
            exp=int(payload["exp"]),
            iss=str(payload["iss"]),
        )
    except (KeyError, ValueError) as exc:
        raise TokenError("malformed refresh token") from exc


def refresh_token_expiry(claims: RefreshTokenClaims) -> datetime:
    return datetime.fromtimestamp(claims.exp, tz=UTC)


def refresh_token_issued_at(claims: RefreshTokenClaims) -> datetime:
    return datetime.fromtimestamp(claims.iat, tz=UTC)


def _decode(token: str, *, expected_typ: str) -> dict[str, object]:
    try:
        payload = jwt.decode(
            token,
            settings.orderflow_jwt_secret,
            algorithms=[settings.orderflow_jwt_alg],
            issuer=settings.orderflow_jwt_issuer,
            options={"require": ["exp", "iat", "iss", "sub"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError("invalid token") from exc

    if payload.get("typ") != expected_typ:
        raise TokenError(f"expected {expected_typ} token")
    return payload


__all__ = [
    "AccessTokenClaims",
    "RefreshTokenClaims",
    "TokenError",
    "decode_access_token",
    "decode_refresh_token",
    "issue_access_token",
    "issue_refresh_token",
    "refresh_token_expiry",
    "refresh_token_issued_at",
]
