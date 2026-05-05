from __future__ import annotations

from collections.abc import Mapping
import logging
from urllib.parse import urlparse
from uuid import UUID

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import (
    DEPLOYMENT_ENVIRONMENT,
    SERVICE_NAME,
    SERVICE_VERSION,
    Resource,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

logger = logging.getLogger("orderflow_api.telemetry")

_configured = False
_SAFE_CACHE_STATUSES = {"hit", "miss_generated", "skipped_completed", "failed"}
_SAFE_CASE_STAGES = {
    "pending",
    "pages_extracting",
    "pages_done",
    "summary_pending",
    "summary_done",
    "action_plan_pending",
    "action_plan_done",
    "review_in_progress",
    "finalized",
    "intake_status",
    "case_dashboard",
}


def configure_tracing(
    *,
    service_name: str,
    service_version: str,
    environment: str,
    otel_endpoint: str | None,
) -> trace.Tracer:
    global _configured

    if _configured:
        return trace.get_tracer("orderflow_api.request")

    resource = Resource.create(
        {
            SERVICE_NAME: service_name,
            SERVICE_VERSION: service_version,
            DEPLOYMENT_ENVIRONMENT: environment,
        }
    )
    provider = TracerProvider(resource=resource)

    if otel_endpoint:
        endpoint, insecure = _normalize_otlp_grpc_endpoint(otel_endpoint)
        exporter = OTLPSpanExporter(endpoint=endpoint, insecure=insecure)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        logger.info("OpenTelemetry tracing enabled for endpoint: %s", endpoint)
    else:
        logger.info("OpenTelemetry endpoint not set. Traces stay local to process.")

    trace.set_tracer_provider(provider)
    _configured = True
    return trace.get_tracer("orderflow_api.request")


def request_trace_attributes(
    path: str,
    query_params: Mapping[str, str] | None = None,
) -> dict[str, str | int | bool]:
    """Build safe request span attributes without including document content."""

    attributes: dict[str, str | int | bool] = {}
    parts = [part for part in path.split("/") if part]
    document_id = _document_id_from_path_parts(parts)
    if document_id is not None:
        attributes["orderflow.document_id"] = document_id

    case_stage = _case_stage_from_path_parts(parts)
    if case_stage is not None:
        attributes["orderflow.workflow.stage"] = case_stage

    if query_params is None:
        return attributes

    page_number = _positive_int(query_params.get("page_number"))
    if page_number is not None:
        attributes["orderflow.page_number"] = page_number

    retry_after_seconds = _positive_int(query_params.get("retry_after_seconds"))
    if retry_after_seconds is not None:
        attributes["orderflow.retry.after_seconds"] = retry_after_seconds

    cache_status = query_params.get("cache_status")
    if cache_status in _SAFE_CACHE_STATUSES:
        attributes["orderflow.cache.status"] = cache_status

    query_stage = query_params.get("stage")
    if query_stage in _SAFE_CASE_STAGES and "orderflow.workflow.stage" not in attributes:
        attributes["orderflow.workflow.stage"] = query_stage

    return attributes


def _normalize_otlp_grpc_endpoint(raw_endpoint: str) -> tuple[str, bool]:
    normalized = raw_endpoint.strip()
    if "://" not in normalized:
        normalized = f"http://{normalized}"

    parsed = urlparse(normalized)
    endpoint = parsed.netloc or parsed.path
    if not endpoint:
        raise ValueError(f"Invalid ORDERFLOW_OTEL_ENDPOINT: {raw_endpoint}")

    insecure = parsed.scheme != "https"
    return endpoint, insecure


def _document_id_from_path_parts(parts: list[str]) -> str | None:
    for resource in ("cases", "documents", "summaries", "annotations"):
        if resource not in parts:
            continue
        index = parts.index(resource)
        if index + 1 >= len(parts):
            continue
        document_id = _uuid_text(parts[index + 1])
        if document_id is not None:
            return document_id
    return None


def _case_stage_from_path_parts(parts: list[str]) -> str | None:
    if "cases" not in parts:
        return None

    index = parts.index("cases")
    suffix = parts[index + 2 :]
    if not suffix:
        return None

    head = suffix[0]
    second = suffix[1] if len(suffix) > 1 else None
    if head == "intake":
        if second == "start":
            return "pages_extracting"
        if second in {"status", "events"}:
            return "intake_status"
    if head == "summary":
        return "summary_pending" if second == "generate" else "summary_done"
    if head == "action-plan":
        if second == "generate":
            return "action_plan_pending"
        if second == "items":
            return "review_in_progress"
        return "action_plan_done"
    if head == "finalize":
        return "finalized"
    if head == "dashboard":
        return "case_dashboard"
    return None


def _uuid_text(value: str) -> str | None:
    try:
        return str(UUID(value))
    except (TypeError, ValueError):
        return None


def _positive_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value > 0:
        return value
    if isinstance(value, str) and value.isdigit():
        parsed = int(value)
        return parsed if parsed > 0 else None
    return None
