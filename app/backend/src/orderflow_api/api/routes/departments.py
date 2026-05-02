"""Department Health Scoring routes (P1-2).

Aggregates persisted documents + obligations into a per-department
health snapshot. Powers the leaderboard dashboard.
"""

from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Depends, Request

from orderflow_api.api.dependencies.auth import require_permission
from orderflow_api.api.document_persistence import list_all_persisted_documents
from orderflow_api.api.extraction_persistence import list_persisted_obligations
from orderflow_api.api.response import success
from orderflow_api.core.auth.permissions import Permission
from orderflow_api.core.department_health import compute_department_health
from orderflow_api.core.risk_service import annotate_obligations_with_risk
from orderflow_api.schemas.departments import (
    DepartmentHealthData,
    DepartmentHealthEnvelope,
    DepartmentHealthItem,
)

router = APIRouter(tags=["departments"])


@router.get("/departments/health", response_model=DepartmentHealthEnvelope)
async def list_department_health_route(
    request: Request,
    _user=Depends(require_permission(Permission.CASE_READ)),
) -> dict[str, object]:
    request_id = getattr(request.state, "request_id", None)

    documents = _safe_list_documents()
    obligations = _safe_list_obligations()
    annotate_obligations_with_risk(obligations)

    obligations_by_doc: dict = defaultdict(list)
    for o in obligations:
        obligations_by_doc[o.document_id].append(o)

    records = compute_department_health(
        documents=documents,
        obligations_by_doc=obligations_by_doc,
        obligations_with_risk=obligations,
    )

    items = [
        DepartmentHealthItem(
            code=r.code,
            name=r.name,
            total_obligations=r.total_obligations,
            completed=r.completed,
            overdue=r.overdue,
            pending_review=r.pending_review,
            open_escalations=r.open_escalations,
            critical_escalations=r.critical_escalations,
            avg_risk_score=r.avg_risk_score,
            compliance_rate=r.compliance_rate,
            breach_rate=r.breach_rate,
            health_score=r.health_score,
            band=r.band,
            rationale=r.rationale,
        )
        for r in records
    ]

    avg = (
        sum(item.health_score for item in items) / len(items) if items else 0.0
    )

    data = DepartmentHealthData(
        total_departments=len(items),
        avg_health_score=round(avg, 1),
        items=items,
    )
    return success(data=data, request_id=request_id, message="department_health")


def _safe_list_documents() -> list:
    try:
        return list_all_persisted_documents()
    except Exception:
        return []


def _safe_list_obligations() -> list:
    try:
        return list_persisted_obligations(document_id=None)
    except Exception:
        return []
