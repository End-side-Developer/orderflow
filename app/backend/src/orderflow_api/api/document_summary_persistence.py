from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from orderflow_api.core.db import get_engine
from orderflow_api.schemas.cases import (
    DocumentSummaryCaseBasics,
    DocumentSummaryData,
    DocumentSummaryDirective,
    DocumentSummaryEntity,
    DocumentSummaryFlowGraph,
    DocumentSummaryImportantDate,
    DocumentSummaryMapData,
    DocumentSummaryResponsibleDepartment,
)


DOCUMENT_SUMMARIES_TABLE = sa.Table(
    "document_summaries",
    sa.MetaData(),
    sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
    sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("case_basics", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column("overview", sa.Text(), nullable=True),
    sa.Column("entities", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column("petitioner", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column("respondent", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column("departments", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column("key_directives", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column("important_dates", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column(
        "responsible_departments",
        postgresql.JSONB(astext_type=sa.Text()),
        nullable=True,
    ),
    sa.Column("flow_graph", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column("map_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column("confidence", sa.Numeric(5, 4), nullable=True),
    sa.Column("prompt_version", sa.String(length=80), nullable=False),
    sa.Column("ai_model", sa.String(length=100), nullable=True),
    sa.Column("ai_provider", sa.String(length=50), nullable=True),
    sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)


def get_document_summary(
    document_id: UUID,
    *,
    prompt_version: str | None = None,
    ai_model: str | None = None,
    ai_provider: str | None = None,
) -> DocumentSummaryData | None:
    """
    Retrieves a cached full-document summary if it exactly matches the extraction context.

    Cache-hit rules for full-document summaries:
    1. `document_id` must match exactly.
    2. `prompt_version` (if provided) must match exactly. Since summaries aggregate pages,
       if the system prompt instructions change, the old summary is considered invalid.
    3. Optional model metadata (`ai_model`, `ai_provider`): If specified, ensures the cached
       summary was produced by the exact same underlying model constraints.

    Cache-hit rules for Action Plans (implicitly tied here):
    Action plans do not have a dedicated monolithic cache table. Instead, action plan generation
    is a one-shot lifecycle stage.
    1. Document-level cache: If `extraction_jobs` marks `action_plan_done`, the action plan is fully
       cached as discrete obligation rows.
    2. Item-level cache bypass: Manual regeneration targets a specific obligation item only,
       updating it in-place and incrementing its `regen_count`.
    """
    filters = [DOCUMENT_SUMMARIES_TABLE.c.document_id == document_id]
    if prompt_version is not None:
        filters.append(DOCUMENT_SUMMARIES_TABLE.c.prompt_version == prompt_version)
    if ai_model is not None:
        filters.append(DOCUMENT_SUMMARIES_TABLE.c.ai_model == ai_model)
    if ai_provider is not None:
        filters.append(DOCUMENT_SUMMARIES_TABLE.c.ai_provider == ai_provider)

    statement = sa.select(DOCUMENT_SUMMARIES_TABLE).where(*filters)
    with get_engine().connect() as connection:
        row = connection.execute(statement).mappings().first()

    if row is None:
        return None
    return _to_document_summary(row)


def upsert_document_summary(
    document_id: UUID,
    *,
    prompt_version: str,
    case_basics: DocumentSummaryCaseBasics | dict[str, Any] | None = None,
    overview: str = "",
    key_directives: list[DocumentSummaryDirective | dict[str, Any]] | None = None,
    important_dates: list[DocumentSummaryImportantDate | dict[str, Any]] | None = None,
    entities_involved: list[DocumentSummaryEntity | dict[str, Any]] | None = None,
    petitioner: dict[str, Any] | None = None,
    respondent: dict[str, Any] | None = None,
    departments: list[dict[str, Any]] | dict[str, Any] | None = None,
    responsible_departments: (
        list[DocumentSummaryResponsibleDepartment | dict[str, Any]] | None
    ) = None,
    flow_graph: DocumentSummaryFlowGraph | dict[str, Any] | None = None,
    map_data: DocumentSummaryMapData | dict[str, Any] | None = None,
    confidence: float | None = None,
    ai_model: str | None = None,
    ai_provider: str | None = None,
) -> DocumentSummaryData:
    now = datetime.now(UTC)
    values = {
        "id": uuid4(),
        "document_id": document_id,
        "case_basics": _serialize_model(case_basics),
        "overview": overview,
        "entities": _serialize_list(entities_involved),
        "petitioner": petitioner,
        "respondent": respondent,
        "departments": departments,
        "key_directives": _serialize_list(key_directives),
        "important_dates": _serialize_list(important_dates),
        "responsible_departments": _serialize_list(responsible_departments),
        "flow_graph": _serialize_model(flow_graph),
        "map_data": _serialize_model(map_data),
        "confidence": confidence,
        "prompt_version": prompt_version,
        "ai_model": ai_model,
        "ai_provider": ai_provider,
        "generated_at": now,
        "created_at": now,
        "updated_at": now,
    }

    statement = postgresql.insert(DOCUMENT_SUMMARIES_TABLE).values(**values)
    update_values = {
        "case_basics": statement.excluded.case_basics,
        "overview": statement.excluded.overview,
        "entities": statement.excluded.entities,
        "petitioner": statement.excluded.petitioner,
        "respondent": statement.excluded.respondent,
        "departments": statement.excluded.departments,
        "key_directives": statement.excluded.key_directives,
        "important_dates": statement.excluded.important_dates,
        "responsible_departments": statement.excluded.responsible_departments,
        "flow_graph": statement.excluded.flow_graph,
        "map_data": statement.excluded.map_data,
        "confidence": statement.excluded.confidence,
        "prompt_version": statement.excluded.prompt_version,
        "ai_model": statement.excluded.ai_model,
        "ai_provider": statement.excluded.ai_provider,
        "generated_at": statement.excluded.generated_at,
        "updated_at": now,
    }
    statement = statement.on_conflict_do_update(
        index_elements=[DOCUMENT_SUMMARIES_TABLE.c.document_id],
        set_=update_values,
    )

    with get_engine().begin() as connection:
        connection.execute(statement)

    summary = get_document_summary(
        document_id,
        prompt_version=prompt_version,
        ai_model=ai_model,
        ai_provider=ai_provider,
    )
    if summary is None:
        raise ValueError(f"Document summary upsert failed for document: {document_id}")
    return summary


def _to_document_summary(row) -> DocumentSummaryData:
    document_id = row["document_id"]
    return DocumentSummaryData(
        id=row["id"],
        document_id=document_id,
        case_basics=row["case_basics"] or {},
        overview=row["overview"] or "",
        key_directives=row["key_directives"] or [],
        important_dates=row["important_dates"] or [],
        entities_involved=row["entities"] or [],
        responsible_departments=row["responsible_departments"] or [],
        flow_graph=_coerce_flow_graph(document_id, row["flow_graph"]),
        map_data=row["map_data"],
        confidence=float(row["confidence"]) if row["confidence"] is not None else None,
        prompt_version=row["prompt_version"],
        ai_model=row["ai_model"],
        ai_provider=row["ai_provider"],
        generated_at=row["generated_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def delete_document_summary(document_id: UUID) -> bool:
    """Delete the cached document summary so the next generation starts fresh.

    Returns True if a row was deleted, False if none existed.
    """
    statement = sa.delete(DOCUMENT_SUMMARIES_TABLE).where(
        DOCUMENT_SUMMARIES_TABLE.c.document_id == document_id
    )
    with get_engine().begin() as connection:
        result = connection.execute(statement)
    return result.rowcount > 0


def _coerce_flow_graph(
    document_id: UUID,
    payload: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if payload is None:
        return None
    if "document_id" in payload:
        return payload
    return {**payload, "document_id": str(document_id)}


def _serialize_list(items: list[Any] | None) -> list[dict[str, Any]]:
    if not items:
        return []
    return [_serialize_model(item) for item in items]


def _serialize_model(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return value
    raise TypeError(f"Unsupported document summary payload type: {type(value)!r}")
