from typing import Any, Literal

from pydantic import BaseModel


class SuccessResponse(BaseModel):
    ok: Literal[True] = True
    message: str = "ok"
    request_id: str | None = None
    data: Any = None


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None


class ErrorResponse(BaseModel):
    ok: Literal[False] = False
    request_id: str | None = None
    error: ErrorDetail
