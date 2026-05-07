from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, EmailStr, Field, model_validator

from orderflow_api.schemas.advocates import AdvocateProfileBase, AdvocateProfileRecord
from orderflow_api.schemas.common import SuccessResponse
from orderflow_api.schemas.users import UserRecord, UserRole


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
    full_name: str = Field(min_length=1, max_length=200)
    role: UserRole
    phone: str | None = Field(default=None, max_length=32)
    preferred_language: str | None = Field(default=None, max_length=8)
    advocate_profile: AdvocateProfileBase | None = None

    @model_validator(mode="after")
    def _check_advocate_profile(self) -> "RegisterRequest":
        if self.role == "advocate" and self.advocate_profile is None:
            raise ValueError("advocate_profile is required when role='advocate'")
        if self.role != "advocate" and self.advocate_profile is not None:
            raise ValueError("advocate_profile is only valid when role='advocate'")
        # Government/judge accounts cannot self-register through the public form;
        # the route layer enforces this with a permission check + admin-only path.
        return self


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=8, max_length=200)


class TokenPayload(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


class LoginData(TokenPayload):
    user: UserRecord
    advocate_profile: AdvocateProfileRecord | None = None


class LoginEnvelope(SuccessResponse):
    data: LoginData


class RefreshData(TokenPayload):
    user: UserRecord
    advocate_profile: AdvocateProfileRecord | None = None


class RefreshEnvelope(SuccessResponse):
    data: RefreshData


class MeData(BaseModel):
    user: UserRecord
    advocate_profile: AdvocateProfileRecord | None = None


class MeEnvelope(SuccessResponse):
    data: MeData


class RegisterData(BaseModel):
    user: UserRecord
    advocate_profile: AdvocateProfileRecord | None = None


class RegisterEnvelope(SuccessResponse):
    data: RegisterData
