import time

from fastapi import APIRouter, Request

from orderflow_api.api.response import success
from orderflow_api.core.config import settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def api_health(request: Request) -> dict[str, object]:
    started_at = getattr(request.app.state, "started_at", None)
    uptime_seconds = int(time.time() - started_at) if isinstance(started_at, (int, float)) else 0
    request_id = getattr(request.state, "request_id", None)

    return success(
        data={
            "service": settings.app_name,
            "version": settings.app_version,
            "environment": settings.orderflow_env,
            "status": "healthy",
            "scope": "api-v1",
            "uptime_seconds": uptime_seconds,
        },
        request_id=request_id,
    )
