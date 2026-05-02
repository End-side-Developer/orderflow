from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from orderflow_api.schemas.common import SuccessResponse


UserRole = Literal["citizen", "advocate", "judge", "government"]
UserStatus = Literal["active", "pending_verification", "suspended", "disabled"]


class UserRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    role: UserRole
    status: UserStatus
    full_name: str
    phone: str | None = None
    preferred_language: str = "en"
    email_verified_at: datetime | None = None
    last_login_at: datetime | None = None
    profile_metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class UserUpdateRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    phone: str | None = Field(default=None, max_length=32)
    preferred_language: str | None = Field(default=None, max_length=8)
    profile_metadata: dict[str, Any] | None = None
    # role/status edits are gated behind permissions in the route, not here.
    role: UserRole | None = None
    status: UserStatus | None = None


class UserEnvelope(SuccessResponse):
    data: UserRecord


class UserListData(BaseModel):
    total: int
    items: list[UserRecord]


class UserListEnvelope(SuccessResponse):
    data: UserListData
