from __future__ import annotations

from datetime import UTC, datetime
from io import BytesIO
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from orderflow_api.api.dependencies.auth import require_permission
from orderflow_api.api.document_persistence import get_persisted_document
from orderflow_api.api.extraction_persistence import list_persisted_obligations
from orderflow_api.api.response import success
from orderflow_api.core.auth.permissions import Permission
from orderflow_api.api.stub_repository import get_document, list_obligations
from orderflow_api.core.config import get_settings
from orderflow_api.core.language_service import is_language_supported
from orderflow_api.core.translation_service import (
    TranslationService,
    TranslationServiceConfig,
)
from orderflow_api.schemas.exports import (
    ActionPlanExportData,
    ActionPlanExportEnvelope,
    ActionPlanExportItem,
    ExportLanguage,
)
from orderflow_api.schemas.obligations import ObligationRecord

router = APIRouter(tags=["exports"])


@router.get("/exports/action-plan", response_model=ActionPlanExportEnvelope)
async def export_action_plan_route(
    request: Request,
    document_id: UUID = Query(...),
    language: str = Query(default="en", min_length=2, max_length=8),
    format: Literal["markdown", "json"] = Query(default="markdown"),
    _user=Depends(require_permission(Permission.CASE_READ)),
):
    request_id = getattr(request.state, "request_id", None)
    normalized_language = _normalize_language_code(language)

    if normalized_language is None or not is_language_supported(normalized_language):
        raise HTTPException(
            status_code=400,
            detail="Unsupported export language. Use one of: en, hi, ta, te, kn, ml, mr",
        )

    obligations = _resolve_obligations_for_document(document_id)
    translated_items = await _build_export_items(
        obligations=obligations,
        target_language=normalized_language,
    )

    export_data = ActionPlanExportData(
        document_id=document_id,
        language=normalized_language,
        generated_at=datetime.now(UTC),
        total=len(translated_items),
        items=translated_items,
    )

    if format == "json":
        return success(
            data=export_data,
            request_id=request_id,
            message="action_plan_export_ready",
        )

    markdown = _render_markdown(export_data)
    filename = f"action-plan-{document_id}-{normalized_language}.md"
    return Response(
        content=markdown,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _resolve_obligations_for_document(document_id: UUID) -> list[ObligationRecord]:
    stub_document = get_document(document_id)
    if stub_document is not None:
        return list_obligations(document_id=document_id)

    persisted_document = _safe_get_persisted_document(document_id)
    if persisted_document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    return _safe_list_persisted_obligations(document_id)


async def _build_export_items(
    obligations: list[ObligationRecord],
    target_language: ExportLanguage,
) -> list[ActionPlanExportItem]:
    if not obligations:
        return []

    translated_titles: list[str] = [obligation.title for obligation in obligations]
    translated_descriptions: list[str | None] = [obligation.description for obligation in obligations]
    translated_owners: list[str | None] = [obligation.owner_hint for obligation in obligations]

    if target_language != "en":
        translated_titles = await _translate_text_list(translated_titles, target_language)
        translated_descriptions = await _translate_optional_text_list(
            translated_descriptions,
            target_language,
        )
        translated_owners = await _translate_optional_text_list(
            translated_owners,
            target_language,
        )

    items: list[ActionPlanExportItem] = []
    for index, obligation in enumerate(obligations):
        citation_span = None
        if obligation.citation is not None:
            citation_span = obligation.citation.clause_span

        items.append(
            ActionPlanExportItem(
                obligation_id=obligation.id,
                title=translated_titles[index],
                description=translated_descriptions[index],
                owner_hint=translated_owners[index],
                due_date=obligation.due_date,
                status=obligation.status,
                priority=obligation.priority,
                review_state=obligation.review_state,
                citation_span=citation_span,
            )
        )

    return items


async def _translate_text_list(values: list[str], target_language: ExportLanguage) -> list[str]:
    if not values:
        return values

    service = _build_translation_service()
    try:
        return await service.translate_batch(values, source_lang="en", target_lang=target_language)
    except Exception:
        return values


async def _translate_optional_text_list(
    values: list[str | None],
    target_language: ExportLanguage,
) -> list[str | None]:
    indexes: list[int] = []
    non_empty_values: list[str] = []

    for index, value in enumerate(values):
        if value is None:
            continue
        cleaned = value.strip()
        if not cleaned:
            continue
        indexes.append(index)
        non_empty_values.append(cleaned)

    if not non_empty_values:
        return values

    translated = await _translate_text_list(non_empty_values, target_language)
    output = list(values)
    for output_index, translated_value in zip(indexes, translated, strict=False):
        output[output_index] = translated_value

    return output


def _build_translation_service() -> TranslationService:
    settings = get_settings()
    return TranslationService(
        config=TranslationServiceConfig(
            service_url=settings.orderflow_translation_service_url,
            api_key=settings.orderflow_translation_api_key,
        ),
        cache_backend=None,
    )


def _render_markdown(data: ActionPlanExportData) -> str:
    buffer = BytesIO()
    buffer.write(f"# Action Plan\n\n".encode("utf-8"))
    buffer.write(f"Document ID: {data.document_id}\n".encode("utf-8"))
    buffer.write(f"Language: {data.language}\n".encode("utf-8"))
    buffer.write(f"Generated At: {data.generated_at.isoformat()}\n\n".encode("utf-8"))

    if not data.items:
        buffer.write("No obligations available for this document.\n".encode("utf-8"))
        return buffer.getvalue().decode("utf-8")

    for index, item in enumerate(data.items, start=1):
        buffer.write(f"## {index}. {item.title}\n".encode("utf-8"))
        if item.description:
            buffer.write(f"- Description: {item.description}\n".encode("utf-8"))
        if item.owner_hint:
            buffer.write(f"- Owner Hint: {item.owner_hint}\n".encode("utf-8"))
        if item.due_date:
            buffer.write(f"- Due Date: {item.due_date.isoformat()}\n".encode("utf-8"))
        buffer.write(f"- Status: {item.status}\n".encode("utf-8"))
        buffer.write(f"- Priority: {item.priority}\n".encode("utf-8"))
        buffer.write(f"- Review State: {item.review_state}\n".encode("utf-8"))
        if item.citation_span:
            buffer.write(f"- Citation: {item.citation_span}\n".encode("utf-8"))
        buffer.write(b"\n")

    return buffer.getvalue().decode("utf-8")


def _normalize_language_code(value: str | None) -> ExportLanguage | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"en", "hi", "ta", "te", "kn", "ml", "mr"}:
        return normalized  # type: ignore[return-value]
    return None


def _safe_get_persisted_document(document_id: UUID):
    try:
        return get_persisted_document(document_id)
    except Exception:
        return None


def _safe_list_persisted_obligations(document_id: UUID):
    try:
        return list_persisted_obligations(document_id=document_id)
    except Exception:
        return []
