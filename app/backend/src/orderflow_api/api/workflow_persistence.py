from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from orderflow_api.core.db import get_engine
from orderflow_api.schemas.workflows import WorkflowRunRecord

WORKFLOW_RUNS_TABLE = sa.Table(
    "workflow_runs",
    sa.MetaData(),
    sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
    sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("workflow_type", sa.String(length=64), nullable=False),
    sa.Column("workflow_id", sa.String(length=255), nullable=False),
    sa.Column("run_id", sa.String(length=255), nullable=False),
    sa.Column("task_queue", sa.String(length=128), nullable=False),
    sa.Column("status", sa.String(length=32), nullable=False),
    sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)


def record_workflow_run(
    document_id: UUID,
    workflow_type: str,
    workflow_id: str,
    run_id: str,
    task_queue: str,
    status: str,
    metadata: dict[str, object] | None,
) -> WorkflowRunRecord:
    now = datetime.now(UTC)
    values = {
        "id": uuid4(),
        "document_id": document_id,
        "workflow_type": workflow_type,
        "workflow_id": workflow_id,
        "run_id": run_id,
        "task_queue": task_queue,
        "status": status,
        "metadata": metadata,
        "started_at": now,
        "completed_at": None,
        "created_at": now,
        "updated_at": now,
    }

    with get_engine().begin() as connection:
        connection.execute(sa.insert(WORKFLOW_RUNS_TABLE).values(**values))

    return WorkflowRunRecord(**values)


def get_workflow_run_by_run_id(run_id: str) -> WorkflowRunRecord | None:
    statement = sa.select(WORKFLOW_RUNS_TABLE).where(WORKFLOW_RUNS_TABLE.c.run_id == run_id)

    with get_engine().connect() as connection:
        row = connection.execute(statement).mappings().first()

    if row is None:
        return None

    return _to_workflow_run_record(row)


def get_latest_workflow_run_for_document(document_id: UUID) -> WorkflowRunRecord | None:
    statement = (
        sa.select(WORKFLOW_RUNS_TABLE)
        .where(WORKFLOW_RUNS_TABLE.c.document_id == document_id)
        .order_by(WORKFLOW_RUNS_TABLE.c.started_at.desc(), WORKFLOW_RUNS_TABLE.c.created_at.desc())
    )

    with get_engine().connect() as connection:
        row = connection.execute(statement).mappings().first()

    if row is None:
        return None

    return _to_workflow_run_record(row)


def list_all_workflow_runs() -> list[WorkflowRunRecord]:
    statement = sa.select(WORKFLOW_RUNS_TABLE).order_by(
        WORKFLOW_RUNS_TABLE.c.started_at.desc(),
        WORKFLOW_RUNS_TABLE.c.created_at.desc(),
    )

    with get_engine().connect() as connection:
        rows = connection.execute(statement).mappings().all()

    return [_to_workflow_run_record(row) for row in rows]


def list_workflow_runs_for_document(document_id: UUID) -> list[WorkflowRunRecord]:
    statement = (
        sa.select(WORKFLOW_RUNS_TABLE)
        .where(WORKFLOW_RUNS_TABLE.c.document_id == document_id)
        .order_by(WORKFLOW_RUNS_TABLE.c.started_at.desc(), WORKFLOW_RUNS_TABLE.c.created_at.desc())
    )

    with get_engine().connect() as connection:
        rows = connection.execute(statement).mappings().all()

    return [_to_workflow_run_record(row) for row in rows]


def update_workflow_run_status(
    run_id: str,
    *,
    status: str,
    completed_at: datetime | None,
    metadata_patch: dict[str, object] | None = None,
) -> WorkflowRunRecord | None:
    now = datetime.now(UTC)
    values: dict[str, object] = {
        "status": status,
        "updated_at": now,
    }
    if completed_at is not None:
        values["completed_at"] = completed_at

    current_record = get_workflow_run_by_run_id(run_id)
    if current_record is None:
        return None

    if metadata_patch is not None:
        existing_metadata = current_record.metadata if isinstance(current_record.metadata, dict) else {}
        values["metadata"] = {**existing_metadata, **metadata_patch}

    statement = (
        sa.update(WORKFLOW_RUNS_TABLE)
        .where(WORKFLOW_RUNS_TABLE.c.run_id == run_id)
        .values(**values)
    )

    with get_engine().begin() as connection:
        result = connection.execute(statement)

    if result.rowcount == 0:
        return None

    return get_workflow_run_by_run_id(run_id)


def _to_workflow_run_record(row) -> WorkflowRunRecord:

    return WorkflowRunRecord(
        id=row["id"],
        document_id=row["document_id"],
        workflow_type=row["workflow_type"],
        workflow_id=row["workflow_id"],
        run_id=row["run_id"],
        task_queue=row["task_queue"],
        status=row["status"],
        metadata=row["metadata"],
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
