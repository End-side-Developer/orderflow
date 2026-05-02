"""Schemas for the CCMS webhook endpoint (P1-5)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class CCMSWebhookEvent(BaseModel):
    reference_id: str = Field(..., min_length=1, max_length=200)
    identifier: str = Field(..., min_length=1, max_length=2000)
    document_type: str = Field(default="judgment", max_length=64)
    delivery_timestamp: datetime | None = None
    source_gateway: str = Field(default="ccms", max_length=64)


class CCMSWebhookRequest(BaseModel):
    events: list[CCMSWebhookEvent] = Field(..., min_length=1, max_length=20)


class CCMSIngestResultItem(BaseModel):
    reference_id: str
    document_id: str | None = None
    status: Literal["ingested", "duplicate", "failed"]
    detail: str = ""


class CCMSWebhookData(BaseModel):
    received: int
    ingested: int
    duplicates: int
    failed: int
    results: list[CCMSIngestResultItem]


class CCMSWebhookEnvelope(BaseModel):
    ok: Literal[True] = True
    message: str = "ok"
    request_id: str | None = None
    data: CCMSWebhookData


class CCMSPollData(BaseModel):
    polled: int
    ingested: int
    duplicates: int
    failed: int
    results: list[CCMSIngestResultItem]


class CCMSPollEnvelope(BaseModel):
    ok: Literal[True] = True
    message: str = "ok"
    request_id: str | None = None
    data: CCMSPollData
