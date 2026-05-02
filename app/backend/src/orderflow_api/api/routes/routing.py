"""Department-Aware Routing routes (P1-1).

Exposes:
- POST /routing/route — score a directive against canonical departments
  and propose officers.
- GET /routing/departments — list canonical departments for the UI.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from orderflow_api.api.dependencies.auth import require_permission
from orderflow_api.api.response import success
from orderflow_api.core.auth.permissions import Permission
from orderflow_api.core.routing_service import (
    _load_departments,
    route_directive,
)
from orderflow_api.schemas.routing import (
    DepartmentDirectoryData,
    DepartmentDirectoryEnvelope,
    DepartmentDirectoryItem,
    DepartmentMatchSchema,
    OfficerSuggestionSchema,
    RouteDirectiveData,
    RouteDirectiveEnvelope,
    RouteDirectiveRequest,
)

router = APIRouter(tags=["routing"])


@router.post("/routing/route", response_model=RouteDirectiveEnvelope)
async def route_route(
    request: Request,
    payload: RouteDirectiveRequest,
    _user=Depends(require_permission(Permission.DEPARTMENT_MANAGE)),
) -> dict[str, object]:
    request_id = getattr(request.state, "request_id", None)
    decision = route_directive(
        payload.text,
        top_n_candidates=payload.top_n_candidates,
        top_officers_per_department=payload.top_officers_per_department,
        confidence_threshold=payload.confidence_threshold,
    )

    data = RouteDirectiveData(
        primary=DepartmentMatchSchema(
            code=decision.primary.code,
            name=decision.primary.name,
            confidence=decision.primary.confidence,
            matched_aliases=decision.primary.matched_aliases,
        )
        if decision.primary is not None
        else None,
        candidates=[
            DepartmentMatchSchema(
                code=c.code,
                name=c.name,
                confidence=c.confidence,
                matched_aliases=c.matched_aliases,
            )
            for c in decision.candidates
        ],
        suggested_officers=[
            OfficerSuggestionSchema(
                id=o.id,
                name=o.name,
                designation=o.designation,
                department_code=o.department_code,
                jurisdiction=o.jurisdiction,
                contact=o.contact,
            )
            for o in decision.suggested_officers
        ],
        multi_department=decision.multi_department,
        rationale=decision.rationale,
    )
    return success(data=data, request_id=request_id, message="directive_routed")


@router.get("/routing/departments", response_model=DepartmentDirectoryEnvelope)
async def list_departments_route(
    request: Request,
    _user=Depends(require_permission(Permission.CASE_READ)),
) -> dict[str, object]:
    request_id = getattr(request.state, "request_id", None)
    items = [
        DepartmentDirectoryItem(
            code=d.get("code", ""),
            name=d.get("name", ""),
            aliases=list(d.get("aliases", []) or []),
        )
        for d in _load_departments()
    ]
    data = DepartmentDirectoryData(total=len(items), items=items)
    return success(data=data, request_id=request_id, message="departments_listed")
