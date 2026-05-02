from __future__ import annotations

import logging
from urllib.parse import urlparse

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
