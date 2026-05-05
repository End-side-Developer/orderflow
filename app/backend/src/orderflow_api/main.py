import logging
import time
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from opentelemetry.trace.status import Status, StatusCode

from orderflow_api.api.response import failure, success
from orderflow_api.api.router import api_router
from orderflow_api.core.config import settings
from orderflow_api.core.telemetry import configure_tracing, request_trace_attributes

logger = logging.getLogger("orderflow_api")


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, version=settings.app_version)
    app.state.started_at = time.time()
    app.state.tracer = configure_tracing(
        service_name=settings.app_name,
        service_version=settings.app_version,
        environment=settings.orderflow_env,
        otel_endpoint=settings.orderflow_otel_endpoint,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_context_middleware(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = request_id
        tracer = request.app.state.tracer

        with tracer.start_as_current_span(f"{request.method} {request.url.path}") as span:
            span.set_attribute("http.method", request.method)
            span.set_attribute("http.target", request.url.path)
            span.set_attribute("http.scheme", request.url.scheme)
            span.set_attribute("orderflow.request_id", request_id)

            client_service = request.headers.get("x-client-service")
            if client_service:
                span.set_attribute("orderflow.client.service", client_service)

            client_path = request.headers.get("x-client-path")
            if client_path:
                span.set_attribute("orderflow.client.path", client_path)

            for key, value in request_trace_attributes(
                request.url.path,
                request.query_params,
            ).items():
                span.set_attribute(key, value)

            try:
                response = await call_next(request)
            except Exception as exc:
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR))
                span.set_attribute("http.status_code", 500)
                raise

            span.set_attribute("http.status_code", response.status_code)
            if response.status_code >= 500:
                span.set_status(Status(StatusCode.ERROR))

            response.headers["x-request-id"] = request_id

            span_context = span.get_span_context()
            if span_context.is_valid:
                response.headers["x-trace-id"] = format(span_context.trace_id, "032x")

            return response

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)

        # Routes can pass a dict detail like
        #   raise HTTPException(
        #       status_code=429,
        #       detail={"code": "gemini_quota_exhausted", "message": "..."},
        #   )
        # to surface a stable machine-readable code (plus optional retry hints) to the UI.
        # String details retain the legacy "http_error" code for backwards compatibility.
        code = "http_error"
        message = "HTTP error"
        details: dict[str, object] = {"status_code": exc.status_code}

        if isinstance(exc.detail, str):
            message = exc.detail
        elif isinstance(exc.detail, dict):
            raw_code = exc.detail.get("code")
            raw_message = exc.detail.get("message")
            if isinstance(raw_code, str) and raw_code:
                code = raw_code
            if isinstance(raw_message, str) and raw_message:
                message = raw_message
            for key in ("retry_after_seconds", "retryable", "provider_detail"):
                if key in exc.detail:
                    details[key] = exc.detail[key]
            extra = exc.detail.get("details")
            if isinstance(extra, dict):
                details.update(extra)

        payload = failure(
            code=code,
            message=message,
            request_id=request_id,
            details=details,
        )
        response = JSONResponse(status_code=exc.status_code, content=payload)
        retry_after = details.get("retry_after_seconds")
        if isinstance(retry_after, int) and retry_after > 0:
            response.headers["retry-after"] = str(retry_after)
        _attach_cors_headers(request, response)
        return response

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception", exc_info=exc)
        request_id = getattr(request.state, "request_id", None)
        payload = failure(
            code="internal_error",
            message="Unexpected server error",
            request_id=request_id,
        )
        response = JSONResponse(status_code=500, content=payload)
        _attach_cors_headers(request, response)
        return response

    @app.get("/health", tags=["health"])
    async def root_health(request: Request) -> dict[str, object]:
        started_at = getattr(request.app.state, "started_at", None)
        uptime_seconds = (
            int(time.time() - started_at) if isinstance(started_at, (int, float)) else 0
        )
        request_id = getattr(request.state, "request_id", None)

        return success(
            data={
                "service": settings.app_name,
                "version": settings.app_version,
                "environment": settings.orderflow_env,
                "status": "healthy",
                "scope": "root",
                "uptime_seconds": uptime_seconds,
            },
            request_id=request_id,
        )

    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app()


def _attach_cors_headers(request: Request, response: JSONResponse) -> None:
    origin = request.headers.get("origin")
    if not origin:
        return

    allowed_origins = settings.cors_origins
    if origin not in allowed_origins:
        return

    response.headers.setdefault("access-control-allow-origin", origin)
    response.headers.setdefault("access-control-allow-credentials", "true")
    vary = response.headers.get("vary")
    if not vary:
        response.headers["vary"] = "Origin"
    elif "origin" not in vary.lower():
        response.headers["vary"] = f"{vary}, Origin"


def run() -> None:
    import uvicorn

    uvicorn.run(
        "orderflow_api.main:app",
        host=settings.orderflow_api_host,
        port=settings.orderflow_api_port,
        reload=False,
    )
