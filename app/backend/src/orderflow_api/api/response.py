from typing import Any

from orderflow_api.schemas.common import ErrorDetail, ErrorResponse, SuccessResponse


def success(data: Any = None, request_id: str | None = None, message: str = "ok") -> dict[str, Any]:
    return SuccessResponse(data=data, request_id=request_id, message=message).model_dump()


def failure(
    code: str,
    message: str,
    request_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    error = ErrorDetail(code=code, message=message, details=details)
    return ErrorResponse(request_id=request_id, error=error).model_dump()
