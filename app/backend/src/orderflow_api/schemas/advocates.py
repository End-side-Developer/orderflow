from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from orderflow_api.schemas.common import SuccessResponse


VerificationStatus = Literal["pending", "verified", "rejected"]
JurisdictionLevel = Literal["supreme", "high_court", "district", "tribunal", "other"]
CaseLinkRole = Literal["counsel", "co-counsel", "consulting"]
CaseLinkStatus = Literal["claimed", "verified"]

ADVOCATE_SPECIALIZATIONS: tuple[str, ...] = (
    "criminal",
    "civil",
    "family",
    "corporate",
    "tax",
    "labour",
    "ipr",
    "consumer",
    "constitutional",
    "other",
)


class Jurisdiction(BaseModel):
    level: JurisdictionLevel
    name: str = Field(min_length=1, max_length=200)
    state: str | None = Field(default=None, max_length=100)


class Education(BaseModel):
    institution: str = Field(min_length=1, max_length=200)
    degree: str = Field(min_length=1, max_length=100)
    year: int | None = Field(default=None, ge=1900, le=2100)


class ContactPreferences(BaseModel):
    email: bool = True
    phone: bool = False
    in_app: bool = True


class Availability(BaseModel):
    days_of_week: list[str] = Field(default_factory=list)
    time_slots: list[str] = Field(default_factory=list)
    lead_time_days: int | None = Field(default=None, ge=0, le=365)


class AdvocateProfileBase(BaseModel):
    bar_council_id: str = Field(min_length=1, max_length=64)
    registration_number: str | None = Field(default=None, max_length=64)
    photo_url: str | None = None
    bio: str | None = None
    years_of_experience: int | None = Field(default=None, ge=0, le=80)
    languages: list[str] = Field(default_factory=list)
    specializations: list[str] = Field(default_factory=list)
    jurisdictions: list[Jurisdiction] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    notable_cases: list[dict[str, Any]] | None = None
    consultation_fee_min_inr: int | None = Field(default=None, ge=0)
    consultation_fee_max_inr: int | None = Field(default=None, ge=0)
    availability: Availability = Field(default_factory=Availability)
    contact_preferences: ContactPreferences = Field(default_factory=ContactPreferences)


class AdvocateProfileRecord(AdvocateProfileBase):
    model_config = ConfigDict(from_attributes=True)

    user_id: UUID
    full_name: str
    verification_status: VerificationStatus
    verified_at: datetime | None = None
    verified_by_user_id: UUID | None = None
    rejection_reason: str | None = None
    ratings_avg: float = 0.0
    ratings_count: int = 0
    created_at: datetime
    updated_at: datetime


class AdvocateDirectoryItem(BaseModel):
    """Light projection used in directory list responses."""

    user_id: UUID
    full_name: str
    photo_url: str | None = None
    years_of_experience: int | None = None
    languages: list[str] = Field(default_factory=list)
    specializations: list[str] = Field(default_factory=list)
    jurisdictions: list[Jurisdiction] = Field(default_factory=list)
    consultation_fee_min_inr: int | None = None
    consultation_fee_max_inr: int | None = None
    ratings_avg: float = 0.0
    ratings_count: int = 0
    verified_at: datetime | None = None
    case_count: int = 0


class AdvocateProfileUpdateRequest(BaseModel):
    photo_url: str | None = None
    bio: str | None = None
    years_of_experience: int | None = Field(default=None, ge=0, le=80)
    languages: list[str] | None = None
    specializations: list[str] | None = None
    jurisdictions: list[Jurisdiction] | None = None
    education: list[Education] | None = None
    notable_cases: list[dict[str, Any]] | None = None
    consultation_fee_min_inr: int | None = Field(default=None, ge=0)
    consultation_fee_max_inr: int | None = Field(default=None, ge=0)
    availability: Availability | None = None
    contact_preferences: ContactPreferences | None = None
    registration_number: str | None = Field(default=None, max_length=64)


class AdvocateRejectRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=2000)


class AdvocateCaseClaimRequest(BaseModel):
    document_id: UUID
    role: CaseLinkRole = "counsel"


class AdvocateCaseLinkRecord(BaseModel):
    id: UUID
    document_id: UUID
    advocate_user_id: UUID
    role: CaseLinkRole
    status: CaseLinkStatus
    created_at: datetime
    verified_at: datetime | None = None
    verified_by_user_id: UUID | None = None
    document_title: str | None = None
    court_name: str | None = None
    order_date: str | None = None
    advocate_full_name: str | None = None
    advocate_photo_url: str | None = None


class AdvocateCaseLinkData(BaseModel):
    item: AdvocateCaseLinkRecord


class AdvocateCaseLinksData(BaseModel):
    total: int
    items: list[AdvocateCaseLinkRecord]


class AdvocateDirectoryData(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[AdvocateDirectoryItem]


class AdvocateDirectoryEnvelope(SuccessResponse):
    data: AdvocateDirectoryData


class AdvocateProfileEnvelope(SuccessResponse):
    data: AdvocateProfileRecord


class AdvocateCaseLinkEnvelope(SuccessResponse):
    data: AdvocateCaseLinkData


class AdvocateCaseLinksEnvelope(SuccessResponse):
    data: AdvocateCaseLinksData
