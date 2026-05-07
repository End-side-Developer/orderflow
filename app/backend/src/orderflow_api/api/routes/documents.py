from __future__ import annotations

import json
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from pydantic import ValidationError

from orderflow_api.api import user_persistence
from orderflow_api.api.dependencies.auth import require_permission
from orderflow_api.api.response import success
from orderflow_api.core.auth.permissions import Permission
from orderflow_api.api.indian_ecourts_lookup import lookup_indian_ecourts_prefill
from orderflow_api.api.extraction_engine import decode_document_text
from orderflow_api.api.ai_extraction import extract_case_flow
from orderflow_api.api.intake_adapter import build_indian_ecourts_document_payload
from orderflow_api.api.page_summary_engine import infer_advocate_specialization_from_signals
from orderflow_api.api.page_summary_persistence import list_page_summaries
from orderflow_api.api.extraction_persistence import list_persisted_obligations
from orderflow_api.api.document_persistence import (
    get_persisted_document,
    persist_uploaded_document,
    list_all_persisted_documents,
    find_document_by_checksum,
    delete_all_documents as delete_all_persisted_documents,
    set_document_case_flow_graph,
)
from orderflow_api.api.stub_repository import (
    create_document,
    get_document,
    ensure_demo_documents,
    delete_all_documents as delete_all_stub_documents,
)
from orderflow_api.core.config import get_settings
from orderflow_api.core.language_service import detect_language
from orderflow_api.core.storage import build_object_storage_client, get_object_bytes
from orderflow_api.schemas.documents import (
    AdvocateRecommendationFilters,
    AdvocateRecommendationsData,
    AdvocateRecommendationsEnvelope,
    CaseFlowData,
    CaseFlowEdge,
    CaseFlowEnvelope,
    CaseFlowNode,
    DocumentAdvocatesData,
    DocumentAdvocatesEnvelope,
    DocumentRecord,
    DocumentCreateRequest,
    DocumentEnvelope,
    DocumentsListEnvelope,
    IndianECourtsIntakeRequest,
    IndianECourtsLookupEnvelope,
    IndianECourtsLookupRequest,
)
from orderflow_api.schemas.advocates import ADVOCATE_SPECIALIZATIONS

import io
from pypdf import PdfReader

router = APIRouter(tags=["documents"])


def _use_stub_repository() -> bool:
    return get_settings().orderflow_api_use_stub_repository


@router.post("/documents", response_model=DocumentEnvelope, status_code=status.HTTP_201_CREATED)
async def create_document_route(
    request: Request,
    payload: DocumentCreateRequest,
    _user=Depends(require_permission(Permission.DOCUMENT_UPLOAD)),
) -> dict[str, object]:
    document = create_document(payload)
    request_id = getattr(request.state, "request_id", None)
    return success(data=document, request_id=request_id, message="document_created")


@router.get("/documents", response_model=DocumentsListEnvelope)
async def list_documents_route(
    request: Request,
    _user=Depends(require_permission(Permission.CASE_READ)),
) -> dict[str, object]:
    request_id = getattr(request.state, "request_id", None)
    if _use_stub_repository():
        documents = ensure_demo_documents()
    else:
        documents = list_all_persisted_documents()
    return success(
        data={
            "total": len(documents),
            "items": documents,
        },
        request_id=request_id,
    )


@router.delete("/documents")
async def delete_all_documents_route(
    request: Request,
    _user=Depends(require_permission(Permission.DOCUMENT_UPLOAD)),
) -> dict[str, object]:
    request_id = getattr(request.state, "request_id", None)
    if _use_stub_repository():
        deleted_count = delete_all_stub_documents()
    else:
        deleted_count = delete_all_persisted_documents()
    return success(
        data={"deleted_count": deleted_count},
        request_id=request_id,
        message=f"Deleted {deleted_count} documents",
    )


@router.get("/documents/{document_id}", response_model=DocumentEnvelope)
async def get_document_route(
    request: Request,
    document_id: UUID,
    _user=Depends(require_permission(Permission.CASE_READ)),
) -> dict[str, object]:
    document = get_document(document_id)
    if document is None:
        document = get_persisted_document(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    request_id = getattr(request.state, "request_id", None)
    return success(data=document, request_id=request_id)


@router.get("/documents/{document_id}/download")
async def download_document_route(
    request: Request,
    document_id: UUID,
    _user=Depends(require_permission(Permission.CASE_READ)),
) -> Response:
    document = get_document(document_id)
    if document is None:
        document = get_persisted_document(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if not document.object_key:
        raise HTTPException(status_code=404, detail="Document file is not available")

    try:
        payload = get_object_bytes(build_object_storage_client(), document.object_key)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Document download failed: {exc}") from exc

    request_id = getattr(request.state, "request_id", None)
    response = Response(
        content=payload,
        media_type=document.source_file_type or "application/octet-stream",
    )
    if request_id:
        response.headers["x-request-id"] = request_id
    response.headers["Content-Disposition"] = f'attachment; filename="{document.source_file_name}"'
    return response


@router.get(
    "/documents/{document_id}/advocates",
    response_model=DocumentAdvocatesEnvelope,
)
async def list_document_advocates_route(
    request: Request,
    document_id: UUID,
    status_filter: str | None = Query(default=None, alias="status", pattern="^(claimed|verified)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _user=Depends(require_permission(Permission.CASE_READ)),
) -> dict[str, object]:
    document = get_document(document_id)
    if document is None:
        document = get_persisted_document(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    total, items = user_persistence.list_document_advocates(
        document_id,
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    request_id = getattr(request.state, "request_id", None)
    payload = DocumentAdvocatesData(document_id=document_id, total=total, items=items)
    return success(data=payload.model_dump(), request_id=request_id, message="document_advocates")


@router.get(
    "/documents/{document_id}/advocate-recommendations",
    response_model=AdvocateRecommendationsEnvelope,
)
async def document_advocate_recommendations_route(
    request: Request,
    document_id: UUID,
    _user=Depends(require_permission(Permission.CASE_READ)),
) -> dict[str, object]:
    document = get_document(document_id)
    if document is None:
        document = get_persisted_document(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    specialization = _derive_document_specialization(document)
    jurisdiction_state = _derive_jurisdiction_state(document)
    jurisdiction_level = _derive_jurisdiction_level(document)
    language = document.auto_detected_language or document.source_language or None

    total, items = user_persistence.list_advocates(
        specialization=specialization,
        jurisdiction_state=jurisdiction_state,
        jurisdiction_level=jurisdiction_level,
        language=language,
        sort="rating",
        only_verified=True,
        limit=5,
        offset=0,
    )

    request_id = getattr(request.state, "request_id", None)
    payload = AdvocateRecommendationsData(
        document_id=document.id,
        total=total,
        filters=AdvocateRecommendationFilters(
            specialization=specialization,
            jurisdiction_state=jurisdiction_state,
            jurisdiction_level=jurisdiction_level,
            language=language,
        ),
        items=items,
    )
    return success(
        data=payload.model_dump(),
        request_id=request_id,
        message="advocate_recommendations",
    )


@router.get(
    "/documents/{document_id}/case-flow",
    response_model=CaseFlowEnvelope,
)
async def get_document_case_flow_route(
    request: Request,
    document_id: UUID,
    _user=Depends(require_permission(Permission.CASE_READ)),
) -> dict[str, object]:
    document = get_document(document_id)
    persisted_document = False
    if document is None:
        document = get_persisted_document(document_id)
        persisted_document = document is not None
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    cached_graph = _coerce_case_flow_graph(getattr(document, "case_flow_graph", None))
    if cached_graph is None:
        summaries = list_page_summaries(document_id)
        obligations = list_persisted_obligations(document_id)
        graph_payload = extract_case_flow(
            metadata=_coerce_metadata(document.metadata),
            summaries=summaries,
            obligations=obligations,
        )
        cached_graph = _coerce_case_flow_graph(graph_payload)
        if persisted_document and cached_graph is not None:
            try:
                set_document_case_flow_graph(document_id, cached_graph)
            except Exception:
                # Rendering the flow is more important than cache persistence.
                pass

    if cached_graph is None:
        nodes = []
        edges = []
    else:
        nodes = [CaseFlowNode.model_validate(item) for item in cached_graph["nodes"]]
        edges = [CaseFlowEdge.model_validate(item) for item in cached_graph["edges"]]

    request_id = getattr(request.state, "request_id", None)
    payload = CaseFlowData(document_id=document_id, nodes=nodes, edges=edges)
    return success(data=payload.model_dump(), request_id=request_id, message="case_flow_graph")


@router.post(
    "/documents/upload",
    response_model=DocumentEnvelope,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document_route(
    request: Request,
    file: UploadFile = File(...),
    metadata: str | None = Form(default=None),
    source_language: str | None = Form(default=None),
    _user=Depends(require_permission(Permission.DOCUMENT_UPLOAD)),
) -> dict[str, object]:
    source_file_name = file.filename or "document.bin"
    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=400, detail="File payload is empty")

    MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
    if len(payload) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File size exceeds maximum allowed size of {MAX_FILE_SIZE // (1024 * 1024)}MB",
        )

    import hashlib

    checksum_sha256 = hashlib.sha256(payload).hexdigest()

    if _use_stub_repository():
        metadata_dict = _parse_metadata(metadata)
        language_metadata = _build_language_metadata(
            payload=payload,
            source_file_type=file.content_type,
            source_file_name=source_file_name,
            source_language_override=source_language,
        )
        metadata_dict = _merge_metadata(metadata_dict, language_metadata)

        pages_total = _count_pdf_pages(payload, file.content_type)
        if pages_total > 0:
            metadata_dict["pages_total"] = pages_total

        document = create_document(
            DocumentCreateRequest(
                source_file_name=source_file_name,
                source_file_type=file.content_type,
                source_file_size=len(payload),
                object_key=None,
                checksum_sha256=checksum_sha256,
                source_language=language_metadata["source_language"],
                auto_detected_language=language_metadata["auto_detected_language"],
                language_confidence=language_metadata["language_confidence"],
                translated_text_stored=language_metadata["translated_text_stored"],
                metadata=metadata_dict,
            )
        )
        request_id = getattr(request.state, "request_id", None)
        return success(data=document, request_id=request_id, message="document_uploaded")

    existing_document = find_document_by_checksum(checksum_sha256)
    if existing_document:
        # Reject the upload outright so the user sees a clear "already
        # ingested" message and can navigate to the existing document
        # instead of re-running extraction on the same content.
        raise HTTPException(
            status_code=409,
            detail={
                "code": "duplicate_document",
                "message": (
                    f"This document was already ingested as "
                    f"'{existing_document.source_file_name}'. Open it from "
                    f"the workbench instead of re-uploading."
                ),
                "details": {
                    "existing_document_id": str(existing_document.id),
                    "existing_source_file_name": existing_document.source_file_name,
                    "checksum_sha256": checksum_sha256,
                },
            },
        )

    metadata_dict = _parse_metadata(metadata)
    language_metadata = _build_language_metadata(
        payload=payload,
        source_file_type=file.content_type,
        source_file_name=source_file_name,
        source_language_override=source_language,
    )
    metadata_dict = _merge_metadata(metadata_dict, language_metadata)

    # Compute PDF page count for intake workflow progress tracking
    pages_total = _count_pdf_pages(payload, file.content_type)
    if pages_total > 0:
        metadata_dict["pages_total"] = pages_total

    try:
        document = persist_uploaded_document(
            source_file_name=source_file_name,
            source_file_type=file.content_type,
            payload=payload,
            metadata=metadata_dict,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Upload persistence failed: {exc}") from exc

    request_id = getattr(request.state, "request_id", None)
    return success(data=document, request_id=request_id, message="document_uploaded")


@router.post(
    "/documents/intake/indian-ecourts/lookup",
    response_model=IndianECourtsLookupEnvelope,
)
async def lookup_indian_ecourts_route(
    request: Request,
    payload: IndianECourtsLookupRequest,
    _user=Depends(require_permission(Permission.DOCUMENT_UPLOAD)),
) -> dict[str, object]:
    try:
        lookup = lookup_indian_ecourts_prefill(payload.identifier)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Indian eCourts lookup failed: {exc}") from exc

    request_id = getattr(request.state, "request_id", None)
    return success(data=lookup, request_id=request_id, message="indian_ecourts_lookup_ready")


@router.post(
    "/documents/intake/indian-ecourts",
    response_model=DocumentEnvelope,
    status_code=status.HTTP_201_CREATED,
)
async def intake_indian_ecourts_route(
    request: Request,
    file: UploadFile = File(...),
    envelope: str = Form(...),
    source_language: str | None = Form(default=None),
    _user=Depends(require_permission(Permission.DOCUMENT_UPLOAD)),
) -> dict[str, object]:
    source_file_name = file.filename or "judgment.pdf"
    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=400, detail="File payload is empty")

    import hashlib

    checksum_sha256 = hashlib.sha256(payload).hexdigest()

    if _use_stub_repository():
        intake_request = _parse_indian_ecourts_envelope(envelope)
        (
            resolved_file_name,
            resolved_file_type,
            metadata,
        ) = build_indian_ecourts_document_payload(
            envelope=intake_request,
            upload_file_name=source_file_name,
            upload_content_type=file.content_type,
        )
        language_metadata = _build_language_metadata(
            payload=payload,
            source_file_type=resolved_file_type,
            source_file_name=resolved_file_name,
            source_language_override=source_language,
        )
        metadata = _merge_metadata(metadata, language_metadata)

        pages_total = _count_pdf_pages(payload, resolved_file_type)
        if pages_total > 0:
            metadata["pages_total"] = pages_total

        document = create_document(
            DocumentCreateRequest(
                source_file_name=resolved_file_name,
                source_file_type=resolved_file_type,
                source_file_size=len(payload),
                object_key=None,
                checksum_sha256=checksum_sha256,
                source_language=language_metadata["source_language"],
                auto_detected_language=language_metadata["auto_detected_language"],
                language_confidence=language_metadata["language_confidence"],
                translated_text_stored=language_metadata["translated_text_stored"],
                metadata=metadata,
            )
        )
        request_id = getattr(request.state, "request_id", None)
        return success(data=document, request_id=request_id, message="indian_ecourts_document_ingested")

    existing_document = find_document_by_checksum(checksum_sha256)
    if existing_document:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "duplicate_document",
                "message": (
                    f"This judgment was already ingested as "
                    f"'{existing_document.source_file_name}'. Open it from "
                    f"the workbench instead of re-uploading."
                ),
                "details": {
                    "existing_document_id": str(existing_document.id),
                    "existing_source_file_name": existing_document.source_file_name,
                    "checksum_sha256": checksum_sha256,
                },
            },
        )

    intake_request = _parse_indian_ecourts_envelope(envelope)
    (
        resolved_file_name,
        resolved_file_type,
        metadata,
    ) = build_indian_ecourts_document_payload(
        envelope=intake_request,
        upload_file_name=source_file_name,
        upload_content_type=file.content_type,
    )
    language_metadata = _build_language_metadata(
        payload=payload,
        source_file_type=resolved_file_type,
        source_file_name=resolved_file_name,
        source_language_override=source_language,
    )
    metadata = _merge_metadata(metadata, language_metadata)

    # Compute PDF page count for intake workflow progress tracking
    pages_total = _count_pdf_pages(payload, resolved_file_type)
    if pages_total > 0:
        metadata["pages_total"] = pages_total

    try:
        document = persist_uploaded_document(
            source_file_name=resolved_file_name,
            source_file_type=resolved_file_type,
            payload=payload,
            metadata=metadata,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Indian eCourts intake persistence failed: {exc}",
        ) from exc

    request_id = getattr(request.state, "request_id", None)
    return success(data=document, request_id=request_id, message="indian_ecourts_document_ingested")


def _parse_metadata(metadata: str | None) -> dict[str, object] | None:
    if metadata is None or not metadata.strip():
        return None

    try:
        payload = json.loads(metadata)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid metadata JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Metadata must be a JSON object")

    return payload


def _derive_document_specialization(document: DocumentRecord) -> str | None:
    metadata = _coerce_metadata(document.metadata)
    cis = _coerce_metadata(metadata.get("cis"))
    additional = _coerce_metadata(metadata.get("additional_metadata"))

    direct_candidates = [
        _normalize_specialization(_coerce_text(metadata.get("inferred_specialization"))),
        _normalize_specialization(_coerce_text(metadata.get("specialization"))),
        _normalize_specialization(_coerce_text(cis.get("case_type"))),
        _normalize_specialization(_coerce_text(additional.get("specialization"))),
    ]
    for candidate in direct_candidates:
        if candidate:
            return candidate

    text_signals: list[str] = []
    for key in ("case_type", "court_name", "bench"):
        value = _coerce_text(cis.get(key))
        if value:
            text_signals.append(value)
    for key in ("subject", "case_topic", "description"):
        value = _coerce_text(additional.get(key))
        if value:
            text_signals.append(value)

    try:
        summaries = list_page_summaries(document.id)
    except Exception:
        summaries = []
    for summary in summaries[:8]:
        if summary.summary:
            text_signals.append(summary.summary)
        if summary.key_points:
            text_signals.extend(summary.key_points[:3])

    inferred = infer_advocate_specialization_from_signals(text=" ".join(text_signals))
    return _normalize_specialization(inferred)


def _derive_jurisdiction_state(document: DocumentRecord) -> str | None:
    metadata = _coerce_metadata(document.metadata)
    cis = _coerce_metadata(metadata.get("cis"))
    additional = _coerce_metadata(metadata.get("additional_metadata"))
    return (
        _coerce_text(cis.get("state"))
        or _coerce_text(additional.get("state"))
        or _coerce_text(metadata.get("state"))
    )


def _derive_jurisdiction_level(document: DocumentRecord) -> str | None:
    metadata = _coerce_metadata(document.metadata)
    cis = _coerce_metadata(metadata.get("cis"))
    court_name = (_coerce_text(cis.get("court_name")) or "").lower()

    if "supreme" in court_name:
        return "supreme"
    if "high court" in court_name:
        return "high_court"
    if "district" in court_name or "sessions" in court_name:
        return "district"
    if "tribunal" in court_name:
        return "tribunal"
    return None


def _normalize_specialization(value: str | None) -> str | None:
    if value is None:
        return None

    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    alias_map = {
        "constitutional_law": "constitutional",
        "criminal_law": "criminal",
        "civil_law": "civil",
        "family_law": "family",
        "labour_law": "labour",
        "labor": "labour",
        "labor_law": "labour",
        "corporate_law": "corporate",
        "consumer_law": "consumer",
        "taxation": "tax",
        "tax_law": "tax",
    }
    normalized = alias_map.get(normalized, normalized)
    if normalized in ADVOCATE_SPECIALIZATIONS:
        return normalized
    return None


def _coerce_metadata(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return value
    return {}


def _coerce_text(value: object) -> str | None:
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    return None


def _coerce_case_flow_graph(value: object) -> dict[str, list[dict[str, object]]] | None:
    if not isinstance(value, dict):
        return None
    nodes = value.get("nodes")
    edges = value.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        return None
    if not all(isinstance(node, dict) for node in nodes):
        return None
    if not all(isinstance(edge, dict) for edge in edges):
        return None
    return {
        "nodes": [dict(node) for node in nodes],
        "edges": [dict(edge) for edge in edges],
    }


def _merge_metadata(
    base: dict[str, object] | None,
    overlay: dict[str, object],
) -> dict[str, object]:
    merged: dict[str, object] = dict(base or {})
    merged.update(overlay)
    return merged


def _build_language_metadata(
    payload: bytes,
    source_file_type: str | None,
    source_file_name: str,
    source_language_override: str | None,
) -> dict[str, object]:
    override_code = _normalize_language_code(source_language_override)
    if source_language_override and override_code is None:
        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid source_language override. " "Supported values: en, hi, ta, te, kn, ml, mr"
            ),
        )

    try:
        raw_text = decode_document_text(payload, source_file_type, source_file_name)
    except ValueError:
        # If text decoding is not possible at upload time, preserve override or default to English.
        return {
            "source_language": override_code or "en",
            "auto_detected_language": None,
            "language_confidence": 0.0,
            "translated_text_stored": False,
        }

    detection = detect_language(raw_text)
    detected_code = _normalize_language_code(detection.detected_language)
    source_language = override_code or detected_code or "en"

    return {
        "source_language": source_language,
        "auto_detected_language": detected_code,
        "language_confidence": round(detection.confidence, 4),
        "translated_text_stored": False,
    }


def _normalize_language_code(value: str | None) -> str | None:
    if value is None:
        return None

    code = value.strip().lower()
    if code in {"en", "hi", "ta", "te", "kn", "ml", "mr"}:
        return code
    return None


def _parse_indian_ecourts_envelope(envelope: str) -> IndianECourtsIntakeRequest:
    if not envelope.strip():
        raise HTTPException(status_code=400, detail="Envelope is required")

    last_errors: list[dict[str, object]] | None = None

    candidates = [envelope]
    try:
        nested_json = json.loads(envelope)
    except json.JSONDecodeError:
        nested_json = None

    if isinstance(nested_json, str):
        candidates.append(nested_json)

    for candidate in candidates:
        try:
            return IndianECourtsIntakeRequest.model_validate_json(candidate)
        except ValidationError as exc:
            last_errors = exc.errors()

    raise HTTPException(
        status_code=400,
        detail={
            "message": "Invalid Indian eCourts envelope",
            "errors": last_errors or [],
        },
    )


def _count_pdf_pages(payload: bytes, source_file_type: str | None) -> int:
    """Return the number of pages in a PDF payload, or 0 if not a PDF."""
    if source_file_type and "pdf" not in source_file_type.lower():
        return 0
    try:
        reader = PdfReader(io.BytesIO(payload))
        return len(reader.pages)
    except Exception:
        return 0
