from __future__ import annotations

from typing import Any

from orderflow_api.schemas.documents import IndianECourtsIntakeRequest


def build_indian_ecourts_document_payload(
    *,
    envelope: IndianECourtsIntakeRequest,
    upload_file_name: str,
    upload_content_type: str | None,
) -> tuple[str, str | None, dict[str, object]]:
    source_file_name = envelope.source_file_name or upload_file_name
    source_file_type = envelope.source_file_type or upload_content_type

    ccms_payload: dict[str, object] = {
        "reference_id": envelope.ccms.reference_id,
        "delivery_timestamp": _serialize_datetime(envelope.ccms.delivery_timestamp),
        "document_type": envelope.ccms.document_type,
        "source_url": envelope.ccms.source_url,
        "source_gateway": envelope.ccms.source_gateway,
        "receipt_id": envelope.ccms.receipt_id,
    }

    cis_payload: dict[str, object] | None = None
    if envelope.cis is not None:
        cis_payload = {
            "case_id": envelope.cis.case_id,
            "court_name": envelope.cis.court_name,
            "court_code": envelope.cis.court_code,
            "order_date": _serialize_date(envelope.cis.order_date),
            "bench": envelope.cis.bench,
            "parties": envelope.cis.parties,
            "petitioners": envelope.cis.petitioners,
            "respondents": envelope.cis.respondents,
            "case_type": envelope.cis.case_type,
            "filing_number": envelope.cis.filing_number,
            "diary_number": envelope.cis.diary_number,
            "judge_names": envelope.cis.judge_names,
            "hearing_stage": envelope.cis.hearing_stage,
            "state": envelope.cis.state,
            "district": envelope.cis.district,
            "department_tags": envelope.cis.department_tags,
        }

    metadata: dict[str, object] = {
        "source_system": "indian_ecourts_service",
        "integration_mode": "read_only_downstream_adapter",
        "intake_channel": "ccms_cis_adapter",
        "ccms": _compact_dict(ccms_payload),
        "cis": _compact_dict(cis_payload),
        "additional_metadata": envelope.additional_metadata,
    }

    return source_file_name, source_file_type, _compact_dict(metadata)


def _serialize_datetime(value: object) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _serialize_date(value: object) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _compact_dict(payload: dict[str, Any] | None) -> dict[str, object] | None:
    if payload is None:
        return None

    compacted: dict[str, object] = {}
    for key, value in payload.items():
        if value is None:
            continue
        if isinstance(value, dict):
            nested = _compact_dict(value)
            if nested:
                compacted[key] = nested
            continue
        if isinstance(value, list):
            filtered = [item for item in value if item is not None]
            if filtered:
                compacted[key] = filtered
            continue
        compacted[key] = value

    return compacted or None
