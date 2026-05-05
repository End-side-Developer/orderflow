from __future__ import annotations

from uuid import uuid4

from orderflow_api.core.telemetry import request_trace_attributes


def test_request_trace_attributes_extract_safe_case_context() -> None:
    document_id = uuid4()
    obligation_id = uuid4()

    attributes = request_trace_attributes(
        f"/api/v1/cases/{document_id}/action-plan/items/{obligation_id}/regenerate",
        {
            "page_number": "3",
            "cache_status": "hit",
            "retry_after_seconds": "15",
            "feedback": "should never become a trace attribute",
        },
    )

    assert attributes == {
        "orderflow.document_id": str(document_id),
        "orderflow.workflow.stage": "review_in_progress",
        "orderflow.page_number": 3,
        "orderflow.retry.after_seconds": 15,
        "orderflow.cache.status": "hit",
    }


def test_request_trace_attributes_ignore_non_uuid_document_segments() -> None:
    attributes = request_trace_attributes(
        "/api/v1/cases/not-a-document-id/summary",
        {"cache_status": "include-secret-value"},
    )

    assert attributes == {"orderflow.workflow.stage": "summary_done"}
