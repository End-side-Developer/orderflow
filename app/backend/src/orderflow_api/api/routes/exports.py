from __future__ import annotations

import base64
from datetime import UTC, datetime
import html
from io import BytesIO
from pathlib import Path
import re
import textwrap
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse

from orderflow_api.api.dependencies.auth import require_permission
from orderflow_api.api.document_persistence import get_persisted_document
from orderflow_api.api.extraction_persistence import list_persisted_obligations
from orderflow_api.api.map_renderer import (
    MapRenderingUnavailable,
    render_page_map,
    render_summary_map,
)
from orderflow_api.api.page_summary_persistence import list_page_summaries
from orderflow_api.api.response import success
from orderflow_api.api.stub_repository import get_document, list_obligations
from orderflow_api.core.auth.permissions import Permission
from orderflow_api.core.config import get_settings
from orderflow_api.core.language_service import is_language_supported
from orderflow_api.core.translation_service import (
    TranslationService,
    TranslationServiceConfig,
)
from orderflow_api.schemas.documents import DocumentRecord
from orderflow_api.schemas.exports import (
    ActionPlanExportData,
    ActionPlanExportEnvelope,
    ActionPlanExportItem,
    CaseBundlePdfRequest,
    ExportLanguage,
)
from orderflow_api.schemas.obligations import ObligationRecord
from orderflow_api.schemas.page_summaries import ExtractedPlace, PageSummaryRecord

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


@router.post("/exports/case-bundle/pdf")
async def export_case_bundle_pdf_route(
    request: Request,
    payload: CaseBundlePdfRequest,
    _user=Depends(require_permission(Permission.EXTRACTION_RUN)),
):
    document = _safe_get_persisted_document(payload.document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    summaries = list_page_summaries(payload.document_id)
    generated_at = datetime.now(UTC)
    context = _build_case_bundle_context(
        document=document,
        summaries=summaries,
        options=payload,
        generated_at=generated_at,
    )
    rendered_html = _render_case_bundle_html(context)
    fallback_text = _render_case_bundle_text(
        document=document,
        summaries=summaries,
        generated_at=generated_at,
    )
    pdf_bytes = _html_to_pdf_bytes(rendered_html, fallback_text=fallback_text)
    filename = f"case-bundle-{_safe_export_name(document.source_file_name, document.id)}.pdf"

    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
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
    translated_descriptions: list[str | None] = [
        obligation.description for obligation in obligations
    ]
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
    buffer.write("# Action Plan\n\n".encode("utf-8"))
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


def _build_case_bundle_context(
    *,
    document: DocumentRecord,
    summaries: list[PageSummaryRecord],
    options: CaseBundlePdfRequest,
    generated_at: datetime,
) -> dict[str, object]:
    all_places = [place for summary in summaries for place in summary.extracted_places]
    summary_map_data_uri = None
    if options.include_summary_map:
        summary_map_data_uri = _png_data_uri(_render_map_safely(all_places, mode="summary"))

    pages: list[dict[str, object]] = []
    for summary in summaries:
        page_map_data_uri = None
        if options.include_per_page_maps:
            page_map_data_uri = _png_data_uri(
                _render_map_safely(
                    summary.extracted_places, mode="page", page_number=summary.page_number
                )
            )
        pages.append({"record": summary, "page_map_data_uri": page_map_data_uri})

    return {
        "document": document,
        "generated_at": generated_at.isoformat(),
        "metadata": _case_bundle_metadata(document),
        "summary_map_data_uri": summary_map_data_uri,
        "pages": pages,
    }


def _render_map_safely(
    places: list[ExtractedPlace],
    *,
    mode: Literal["summary", "page"],
    page_number: int | None = None,
) -> bytes:
    try:
        if mode == "summary":
            return render_summary_map(places)
        if page_number is None:
            return b""
        return render_page_map(places, page_number=page_number)
    except MapRenderingUnavailable:
        return b""


def _png_data_uri(payload: bytes) -> str | None:
    if not payload:
        return None
    encoded = base64.b64encode(payload).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _case_bundle_metadata(document: DocumentRecord) -> dict[str, str | None]:
    metadata = document.metadata or {}
    cis = metadata.get("cis") if isinstance(metadata.get("cis"), dict) else {}
    source = {**metadata, **cis}
    return {
        "court_name": _string_or_none(source.get("court_name")),
        "state": _string_or_none(source.get("state")),
        "district": _string_or_none(source.get("district")),
        "order_date": _string_or_none(source.get("order_date")),
        "case_id": _string_or_none(source.get("case_id")),
    }


def _string_or_none(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _render_case_bundle_html(context: dict[str, object]) -> str:
    template_dir = Path(__file__).resolve().parents[2] / "templates"
    try:
        from jinja2 import Environment, FileSystemLoader, select_autoescape
    except Exception:
        return _render_fallback_html(context)

    environment = Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = environment.get_template("case_bundle.html")
    return template.render(**context)


def _render_fallback_html(context: dict[str, object]) -> str:
    document = context["document"]
    pages = context["pages"]
    return "\n".join(
        [
            "<html><body>",
            "<h1>OrderFlow Case Bundle</h1>",
            f"<p>{html.escape(str(getattr(document, 'source_file_name', 'document')))}</p>",
            *[
                f"<h2>Page {html.escape(str(page['record'].page_number))}</h2>"
                f"<p>{html.escape(str(page['record'].summary))}</p>"
                for page in pages  # type: ignore[union-attr]
            ],
            "</body></html>",
        ]
    )


def _html_to_pdf_bytes(rendered_html: str, *, fallback_text: str) -> bytes:
    try:
        from weasyprint import HTML

        return HTML(string=rendered_html).write_pdf()
    except Exception:
        return _minimal_pdf(fallback_text)


def _render_case_bundle_text(
    *,
    document: DocumentRecord,
    summaries: list[PageSummaryRecord],
    generated_at: datetime,
) -> str:
    lines = [
        "OrderFlow Case Bundle",
        f"Document: {document.source_file_name}",
        f"Document ID: {document.id}",
        f"Generated At: {generated_at.isoformat()}",
        "",
    ]
    if not summaries:
        lines.append("No page summaries are available for this document.")
    for summary in summaries:
        lines.extend(
            [
                f"Page {summary.page_number}",
                summary.summary,
                *[f"- {point}" for point in summary.key_points],
                "",
            ]
        )
    return "\n".join(lines)


def _minimal_pdf(text: str) -> bytes:
    wrapped_lines: list[str] = []
    for line in text.splitlines() or ["OrderFlow Case Bundle"]:
        wrapped_lines.extend(textwrap.wrap(line, width=88) or [""])
    wrapped_lines = wrapped_lines[:52]

    content_lines = ["BT", "/F1 10 Tf", "50 800 Td", "14 TL"]
    for line in wrapped_lines:
        content_lines.append(f"({_escape_pdf_text(line)}) Tj")
        content_lines.append("T*")
    content_lines.append("ET")
    content_stream = "\n".join(content_lines).encode("latin-1", errors="replace")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"
        ),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length "
        + str(len(content_stream)).encode("ascii")
        + b" >>\nstream\n"
        + content_stream
        + b"\nendstream",
    ]

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{index} 0 obj\n".encode("ascii"))
        pdf.extend(obj)
        pdf.extend(b"\nendobj\n")

    xref_start = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        (
            f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_start}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(pdf)


def _escape_pdf_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _safe_export_name(source_file_name: str, document_id: UUID) -> str:
    stem = source_file_name.rsplit(".", 1)[0] if source_file_name else str(document_id)
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip("-._")
    return (cleaned or str(document_id))[:80]


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
