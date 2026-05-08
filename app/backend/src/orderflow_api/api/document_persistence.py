from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import re
from decimal import Decimal
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from orderflow_api.core.db import get_engine
from orderflow_api.core.storage import build_object_storage_client, put_object
from orderflow_api.schemas.documents import DocumentRecord

DOCUMENTS_TABLE = sa.Table(
    "documents",
    sa.MetaData(),
    sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
    sa.Column("source_file_name", sa.String(length=255), nullable=False),
    sa.Column("source_file_type", sa.String(length=100), nullable=True),
    sa.Column("source_file_size", sa.BigInteger(), nullable=True),
    sa.Column("object_key", sa.String(length=512), nullable=True),
    sa.Column("checksum_sha256", sa.String(length=64), nullable=True),
    sa.Column("workflow_run_id", sa.String(length=255), nullable=True),
    sa.Column("status", sa.String(length=32), nullable=False),
    sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column("case_flow_graph", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column("source_language", sa.String(length=8), nullable=False),
    sa.Column("auto_detected_language", sa.String(length=8), nullable=True),
    sa.Column("language_confidence", sa.Numeric(5, 4), nullable=False),
    sa.Column("translated_text_stored", sa.Boolean(), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)


def persist_uploaded_document(
    source_file_name: str,
    source_file_type: str | None,
    payload: bytes,
    metadata: dict[str, object] | None,
) -> DocumentRecord:
    document_id = uuid4()
    safe_file_name = _sanitize_file_name(source_file_name)
    object_key = f"documents/{document_id}/{safe_file_name}"
    checksum_sha256 = hashlib.sha256(payload).hexdigest()
    source_file_size = len(payload)
    now = datetime.now(UTC)

    client = build_object_storage_client()
    put_object(
        client=client,
        object_key=object_key,
        payload=payload,
        content_type=source_file_type,
    )

    source_language = _extract_supported_language(
        metadata.get("source_language") if metadata else None,
        default="en",
    )
    auto_detected_language = _extract_supported_language(
        metadata.get("auto_detected_language") if metadata else None,
        default=None,
    )
    language_confidence = _extract_language_confidence(
        metadata.get("language_confidence") if metadata else None,
        default=1.0,
    )
    translated_text_stored = bool(metadata.get("translated_text_stored")) if metadata else False

    values = {
        "id": document_id,
        "source_file_name": source_file_name,
        "source_file_type": source_file_type,
        "source_file_size": source_file_size,
        "object_key": object_key,
        "checksum_sha256": checksum_sha256,
        "workflow_run_id": None,
        "status": "uploaded",
        "metadata": metadata,
        "case_flow_graph": None,
        "source_language": source_language,
        "auto_detected_language": auto_detected_language,
        "language_confidence": language_confidence,
        "translated_text_stored": translated_text_stored,
        "created_at": now,
        "updated_at": now,
    }

    with get_engine().begin() as connection:
        connection.execute(sa.insert(DOCUMENTS_TABLE).values(**values))

    return DocumentRecord(**values)


def get_persisted_document(document_id: UUID) -> DocumentRecord | None:
    statement = sa.select(DOCUMENTS_TABLE).where(DOCUMENTS_TABLE.c.id == document_id)
    with get_engine().connect() as connection:
        row = connection.execute(statement).mappings().first()

    if row is None:
        return None

    return DocumentRecord(
        id=row["id"],
        source_file_name=row["source_file_name"],
        source_file_type=row["source_file_type"],
        source_file_size=row["source_file_size"],
        object_key=row["object_key"],
        checksum_sha256=row["checksum_sha256"],
        workflow_run_id=row.get("workflow_run_id"),
        status=row["status"],
        metadata=row["metadata"],
        case_flow_graph=row.get("case_flow_graph"),
        source_language=_extract_supported_language(row.get("source_language"), default="en"),
        auto_detected_language=_extract_supported_language(
            row.get("auto_detected_language"),
            default=None,
        ),
        language_confidence=float(row.get("language_confidence") or 1.0),
        translated_text_stored=bool(row.get("translated_text_stored") or False),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def set_document_workflow_run_id(document_id: UUID, workflow_run_id: str) -> None:
    statement = (
        sa.update(DOCUMENTS_TABLE)
        .where(DOCUMENTS_TABLE.c.id == document_id)
        .values(workflow_run_id=workflow_run_id, updated_at=datetime.now(UTC))
    )

    with get_engine().begin() as connection:
        result = connection.execute(statement)

    if result.rowcount == 0:
        raise ValueError(f"Document not found: {document_id}")


def set_document_case_flow_graph(document_id: UUID, case_flow_graph: dict[str, object]) -> None:
    statement = (
        sa.update(DOCUMENTS_TABLE)
        .where(DOCUMENTS_TABLE.c.id == document_id)
        .values(case_flow_graph=case_flow_graph, updated_at=datetime.now(UTC))
    )

    with get_engine().begin() as connection:
        result = connection.execute(statement)

    if result.rowcount == 0:
        raise ValueError(f"Document not found: {document_id}")


def _sanitize_file_name(file_name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", file_name.strip())
    return cleaned or "document.bin"


def _extract_supported_language(value: object, default: str | None) -> str | None:
    allowed = {"en", "hi", "ta", "te", "kn", "ml", "mr"}
    if isinstance(value, str):
        code = value.strip().lower()
        if code in allowed:
            return code
    return default


def _extract_language_confidence(value: object, default: float) -> float:
    if isinstance(value, Decimal):
        number = float(value)
    elif isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        try:
            number = float(value)
        except ValueError:
            return default
    else:
        return default

    if number < 0:
        return 0.0
    if number > 1:
        return 1.0
    return number


def list_all_persisted_documents() -> list[DocumentRecord]:
    statement = sa.select(DOCUMENTS_TABLE).order_by(DOCUMENTS_TABLE.c.created_at.desc())
    with get_engine().connect() as connection:
        rows = connection.execute(statement).mappings().fetchall()

    return [
        DocumentRecord(
            id=row["id"],
            source_file_name=row["source_file_name"],
            source_file_type=row["source_file_type"],
            source_file_size=row["source_file_size"],
            object_key=row["object_key"],
            checksum_sha256=row["checksum_sha256"],
            workflow_run_id=row.get("workflow_run_id"),
            status=row["status"],
            metadata=row["metadata"],
            case_flow_graph=row.get("case_flow_graph"),
            source_language=_extract_supported_language(row.get("source_language"), default="en"),
            auto_detected_language=_extract_supported_language(
                row.get("auto_detected_language"),
                default=None,
            ),
            language_confidence=float(row.get("language_confidence") or 1.0),
            translated_text_stored=bool(row.get("translated_text_stored") or False),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
        for row in rows
    ]


def find_document_by_checksum(checksum_sha256: str) -> DocumentRecord | None:
    statement = sa.select(DOCUMENTS_TABLE).where(
        DOCUMENTS_TABLE.c.checksum_sha256 == checksum_sha256
    )
    with get_engine().connect() as connection:
        row = connection.execute(statement).mappings().first()

    if row is None:
        return None

    return DocumentRecord(
        id=row["id"],
        source_file_name=row["source_file_name"],
        source_file_type=row["source_file_type"],
        source_file_size=row["source_file_size"],
        object_key=row["object_key"],
        checksum_sha256=row["checksum_sha256"],
        workflow_run_id=row.get("workflow_run_id"),
        status=row["status"],
        metadata=row["metadata"],
        case_flow_graph=row.get("case_flow_graph"),
        source_language=_extract_supported_language(row.get("source_language"), default="en"),
        auto_detected_language=_extract_supported_language(
            row.get("auto_detected_language"),
            default=None,
        ),
        language_confidence=float(row.get("language_confidence") or 1.0),
        translated_text_stored=bool(row.get("translated_text_stored") or False),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def delete_all_documents() -> int:
    statement = sa.delete(DOCUMENTS_TABLE)
    with get_engine().begin() as connection:
        result = connection.execute(statement)
    return result.rowcount


def delete_persisted_document(document_id: UUID) -> bool:
    """
    Atomically delete a single document and all dependent rows.

    All FKs that point at `documents.id` use `ON DELETE CASCADE` (clauses,
    obligations, page_summaries, page_annotations, document_summaries,
    document_text_boxes, extraction_jobs, workflow_runs, case_advocates),
    so a single DELETE on the parent cascades through every child table.

    The associated blob is also removed on a best-effort basis. Storage
    failures do not block the database deletion.

    Returns True if a row was deleted, False if no document with that id
    existed.
    """
    document = get_persisted_document(document_id)
    if document is None:
        return False

    if document.object_key:
        try:
            from orderflow_api.core.storage import (
                build_object_storage_client,
                delete_object,
            )

            client = build_object_storage_client()
            delete_object(client, document.object_key)
        except Exception as exc:
            # Storage cleanup is best-effort — log and continue so a stuck
            # blob never blocks a case-deletion request.
            print(
                f"warn: failed to delete blob '{document.object_key}' for "
                f"document {document_id}: {exc}"
            )

    statement = sa.delete(DOCUMENTS_TABLE).where(DOCUMENTS_TABLE.c.id == document_id)
    with get_engine().begin() as connection:
        result = connection.execute(statement)
    return result.rowcount > 0
