from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import math
import re
from typing import Iterable
from uuid import UUID

from orderflow_api.api.document_persistence import (
    get_persisted_document,
    list_all_persisted_documents,
)
from orderflow_api.api.extraction_persistence import (
    list_persisted_obligations,
    list_recent_persisted_obligation_audit_events,
)
from orderflow_api.api.workflow_persistence import (
    list_all_workflow_runs,
)
from orderflow_api.schemas.documents import DocumentRecord
from orderflow_api.schemas.obligations import ObligationAuditEvent, ObligationRecord
from orderflow_api.schemas.workbench import (
    WorkbenchActivityItem,
    WorkbenchDocumentCard,
    WorkbenchDocumentData,
    WorkbenchDocumentMetrics,
    WorkbenchNextAction,
    WorkbenchOverviewData,
    WorkbenchRelatedCase,
    WorkbenchSummary,
)


_TOKEN_PATTERN = re.compile(r"[a-z0-9]{4,}")
_SIMILARITY_STOPWORDS = {
    "shall",
    "must",
    "within",
    "thereof",
    "court",
    "order",
    "judgment",
    "document",
    "respondent",
    "petitioner",
    "appellant",
}
_PRESSURE_RANK = {
    "stable": 0,
    "watch": 1,
    "urgent": 2,
    "critical": 3,
}


def build_workbench_overview() -> WorkbenchOverviewData:
    documents = list_all_persisted_documents()
    obligations = list_persisted_obligations(document_id=None)
    workflows = list_all_workflow_runs()
    recent_audit = list_recent_persisted_obligation_audit_events(limit=12)

    latest_workflow_by_document = _latest_workflow_by_document(workflows)
    grouped_obligations = _group_obligations_by_document(obligations)
    cards = [
        _build_document_card(
            document=document,
            obligations=grouped_obligations.get(document.id, []),
            workflow=latest_workflow_by_document.get(document.id),
            recent_activity_at=_latest_activity_at(
                grouped_obligations.get(document.id, []),
                recent_audit,
            ),
        )
        for document in documents
    ]

    cards.sort(
        key=lambda card: (
            _PRESSURE_RANK[card.pressure_level],
            card.metrics.pending_review + card.metrics.open_escalations,
            card.last_activity_at or card.updated_at,
        ),
        reverse=True,
    )

    summary = WorkbenchSummary(
        total_documents=len(documents),
        ready_documents=sum(1 for card in cards if card.status == "ready"),
        in_flight_documents=sum(1 for card in cards if card.workflow_status == "started"),
        pending_review=sum(card.metrics.pending_review for card in cards),
        open_escalations=sum(card.metrics.open_escalations for card in cards),
        critical_escalations=sum(card.metrics.critical_escalations for card in cards),
        total_obligations=sum(card.metrics.total_obligations for card in cards),
    )

    return WorkbenchOverviewData(
        summary=summary,
        documents=cards,
        recent_activity=_build_activity_feed(recent_audit, grouped_obligations, documents),
    )


def build_document_workbench(document_id: UUID) -> WorkbenchDocumentData | None:
    document = get_persisted_document(document_id)
    if document is None:
        return None

    obligations = list_persisted_obligations(document_id=None)
    workflows = list_all_workflow_runs()
    latest_workflow = _latest_workflow_by_document(workflows).get(document_id)
    grouped_obligations = _group_obligations_by_document(obligations)
    document_obligations = grouped_obligations.get(document_id, [])
    recent_audit = list_recent_persisted_obligation_audit_events(limit=10, document_id=document_id)

    card = _build_document_card(
        document=document,
        obligations=document_obligations,
        workflow=latest_workflow,
        recent_activity_at=_latest_activity_at(document_obligations, recent_audit),
    )

    return WorkbenchDocumentData(
        document=card,
        related_cases=_build_related_cases(
            document,
            document_obligations,
            documents=list_all_persisted_documents(),
            grouped_obligations=grouped_obligations,
        ),
        next_actions=_build_next_actions(card),
        recent_activity=_build_activity_feed(recent_audit, grouped_obligations, [document]),
    )


def _group_obligations_by_document(
    obligations: Iterable[ObligationRecord],
) -> dict[UUID, list[ObligationRecord]]:
    grouped: dict[UUID, list[ObligationRecord]] = defaultdict(list)
    for obligation in obligations:
        grouped[obligation.document_id].append(obligation)
    return grouped


def _latest_workflow_by_document(workflows):
    latest: dict[UUID, object] = {}
    for workflow in workflows:
        current = latest.get(workflow.document_id)
        if current is None or workflow.started_at > current.started_at:
            latest[workflow.document_id] = workflow
    return latest


def _build_document_card(
    *,
    document: DocumentRecord,
    obligations: list[ObligationRecord],
    workflow,
    recent_activity_at: datetime | None,
) -> WorkbenchDocumentCard:
    metrics = WorkbenchDocumentMetrics(
        total_obligations=len(obligations),
        pending_review=sum(1 for item in obligations if item.review_state == "pending_review"),
        approved=sum(1 for item in obligations if item.review_state == "approved"),
        rejected=sum(1 for item in obligations if item.review_state == "rejected"),
        completed=sum(1 for item in obligations if item.status == "completed"),
        open_escalations=sum(
            1 for item in obligations if bool(item.escalation and item.escalation.open)
        ),
        critical_escalations=sum(
            1
            for item in obligations
            if bool(
                item.escalation and item.escalation.open and item.escalation.level == "critical"
            )
        ),
    )

    pressure_level = _derive_pressure_level(metrics)
    stage = _derive_stage(
        document.status, workflow.status if workflow is not None else None, metrics
    )
    next_action = _derive_next_action(stage, metrics)
    metadata = document.metadata if isinstance(document.metadata, dict) else {}
    cis = metadata.get("cis") if isinstance(metadata.get("cis"), dict) else {}
    additional = (
        metadata.get("additional_metadata")
        if isinstance(metadata.get("additional_metadata"), dict)
        else {}
    )

    last_activity_at = max(
        [
            moment
            for moment in [
                recent_activity_at,
                workflow.updated_at if workflow else None,
                document.updated_at,
            ]
            if moment is not None
        ],
        default=document.updated_at,
    )

    return WorkbenchDocumentCard(
        document_id=document.id,
        source_file_name=document.source_file_name,
        source_language=document.source_language,
        status=document.status,
        workflow_status=workflow.status if workflow is not None else None,
        pressure_level=pressure_level,
        stage=stage,
        next_action=next_action,
        department=_coerce_text(additional.get("department")),
        court_name=_coerce_text(cis.get("court_name")),
        created_at=document.created_at,
        updated_at=document.updated_at,
        last_activity_at=last_activity_at,
        metrics=metrics,
    )


def _derive_pressure_level(metrics: WorkbenchDocumentMetrics):
    if metrics.critical_escalations > 0:
        return "critical"
    if metrics.pending_review >= 3 or metrics.open_escalations >= 2:
        return "urgent"
    if metrics.pending_review > 0 or metrics.open_escalations > 0:
        return "watch"
    return "stable"


def _derive_stage(
    document_status: str, workflow_status: str | None, metrics: WorkbenchDocumentMetrics
):
    if workflow_status == "started":
        return "intake_running"
    if metrics.total_obligations == 0 and document_status in {"uploaded", "processing"}:
        return "ready_for_extraction"
    if metrics.pending_review > 0:
        return "review_gate"
    if metrics.critical_escalations > 0 or metrics.open_escalations > 0:
        return "execution_risk"
    if metrics.total_obligations > 0 and metrics.completed == metrics.total_obligations:
        return "closure_ready"
    return "execution"


def _derive_next_action(stage: str, metrics: WorkbenchDocumentMetrics) -> str:
    if stage == "intake_running":
        return "Monitor workflow completion and confirm extraction output."
    if stage == "ready_for_extraction":
        return "Run extraction to generate the obligation ledger."
    if stage == "review_gate":
        return f"Resolve {metrics.pending_review} pending review item(s) before execution."
    if stage == "execution_risk":
        return "Escalate breach-risk obligations and attach proof-ready evidence."
    if stage == "closure_ready":
        return "Package proof and finalize the verified action plan."
    return "Drive owner assignment and evidence collection on approved actions."


def _build_activity_feed(
    audit_events: list[ObligationAuditEvent],
    grouped_obligations: dict[UUID, list[ObligationRecord]],
    documents: list[DocumentRecord],
) -> list[WorkbenchActivityItem]:
    document_names = {document.id: document.source_file_name for document in documents}
    obligation_index = {
        obligation.id: obligation
        for obligations in grouped_obligations.values()
        for obligation in obligations
    }
    activity: list[WorkbenchActivityItem] = []

    for event in audit_events:
        obligation = obligation_index.get(event.obligation_id)
        if obligation is None:
            continue

        level = _derive_activity_level(obligation)
        title = obligation.title or document_names.get(obligation.document_id, "Obligation update")
        detail = _format_audit_detail(event)
        activity.append(
            WorkbenchActivityItem(
                title=title,
                document_id=obligation.document_id,
                obligation_id=obligation.id,
                action=event.action,
                actor_type=event.actor_type,
                created_at=event.created_at,
                level=level,
                detail=detail,
            )
        )

    return activity


def _derive_activity_level(obligation: ObligationRecord):
    escalation = obligation.escalation
    if escalation and escalation.open and escalation.level == "critical":
        return "critical"
    if obligation.review_state == "pending_review":
        return "watch"
    if escalation and escalation.open:
        return "urgent"
    return "stable"


def _format_audit_detail(event: ObligationAuditEvent) -> str | None:
    if not isinstance(event.payload, dict):
        return None

    parts = []
    for key in ("review_state", "status", "owner_hint"):
        value = event.payload.get(key)
        if value:
            parts.append(f"{key.replace('_', ' ')}: {value}")

    return " | ".join(parts) if parts else None


def _latest_activity_at(
    obligations: list[ObligationRecord],
    audit_events: list[ObligationAuditEvent],
) -> datetime | None:
    obligation_ids = {obligation.id for obligation in obligations}
    timestamps = [
        event.created_at for event in audit_events if event.obligation_id in obligation_ids
    ]
    return max(timestamps, default=None)


def _build_next_actions(card: WorkbenchDocumentCard) -> list[WorkbenchNextAction]:
    actions: list[WorkbenchNextAction] = []

    if card.metrics.pending_review > 0:
        actions.append(
            WorkbenchNextAction(
                priority="critical" if card.metrics.critical_escalations > 0 else "high",
                title="Clear the human-review gate",
                detail=f"{card.metrics.pending_review} obligation(s) still need reviewer approval or rejection.",
            )
        )

    if card.metrics.critical_escalations > 0:
        actions.append(
            WorkbenchNextAction(
                priority="critical",
                title="Escalate breach-risk obligations",
                detail=f"{card.metrics.critical_escalations} obligation(s) are already in critical escalation state.",
            )
        )

    if card.metrics.open_escalations > 0 and card.metrics.critical_escalations == 0:
        actions.append(
            WorkbenchNextAction(
                priority="high",
                title="Resolve watchlist pressure",
                detail=f"{card.metrics.open_escalations} obligation(s) have open escalation signals that need evidence or owner correction.",
            )
        )

    if card.workflow_status == "started":
        actions.append(
            WorkbenchNextAction(
                priority="medium",
                title="Track the active workflow run",
                detail="The intake workflow is still running; keep the reviewer board open for fresh obligations.",
            )
        )

    if card.metrics.approved > 0 and card.metrics.completed < card.metrics.approved:
        actions.append(
            WorkbenchNextAction(
                priority="medium",
                title="Move approved items into proof collection",
                detail="Approved obligations exist without closure; start gathering evidence packets and verification receipts.",
            )
        )

    if not actions:
        actions.append(
            WorkbenchNextAction(
                priority="medium",
                title="Keep the case execution-ready",
                detail="No blockers are open right now; use this window to tighten proof quality and audit notes.",
            )
        )

    return actions[:4]


def _build_related_cases(
    active_document: DocumentRecord,
    active_obligations: list[ObligationRecord],
    *,
    documents: list[DocumentRecord],
    grouped_obligations: dict[UUID, list[ObligationRecord]],
) -> list[WorkbenchRelatedCase]:
    # P1-3: try pgvector semantic similarity first; fall back to token overlap
    # if the vector index is unavailable or yields nothing.
    vector_results = _related_cases_by_vector(
        active_document=active_document,
        active_obligations=active_obligations,
        documents=documents,
        grouped_obligations=grouped_obligations,
    )
    if vector_results:
        return vector_results

    active_tokens = _document_tokens(active_document, active_obligations)
    if not active_tokens:
        return []

    active_owners = {
        item.owner_hint.strip().lower()
        for item in active_obligations
        if isinstance(item.owner_hint, str) and item.owner_hint.strip()
    }
    active_priorities = {item.priority for item in active_obligations}

    recommendations: list[WorkbenchRelatedCase] = []
    for document in documents:
        if document.id == active_document.id:
            continue

        candidate_obligations = grouped_obligations.get(document.id, [])
        candidate_tokens = _document_tokens(document, candidate_obligations)
        if not candidate_tokens:
            continue

        overlap = active_tokens & candidate_tokens
        if not overlap:
            continue

        owner_overlap = any(
            isinstance(item.owner_hint, str) and item.owner_hint.strip().lower() in active_owners
            for item in candidate_obligations
        )
        priority_overlap = any(item.priority in active_priorities for item in candidate_obligations)
        denominator = math.sqrt(len(active_tokens) * len(candidate_tokens)) or 1.0
        similarity_score = len(overlap) / denominator
        similarity_score += 0.18 if owner_overlap else 0.0
        similarity_score += 0.08 if priority_overlap else 0.0

        open_escalations = sum(
            1 for item in candidate_obligations if bool(item.escalation and item.escalation.open)
        )
        critical_escalations = sum(
            1
            for item in candidate_obligations
            if bool(
                item.escalation and item.escalation.open and item.escalation.level == "critical"
            )
        )
        pressure = (
            "critical"
            if critical_escalations > 0
            else "watch" if open_escalations > 0 else "stable"
        )
        rationale_tags = [f"pattern:{token}" for token in sorted(overlap)[:3]]
        if owner_overlap:
            rationale_tags.append("owner-overlap")
        if priority_overlap:
            rationale_tags.append("priority-overlap")

        recommendations.append(
            WorkbenchRelatedCase(
                document_id=document.id,
                source_file_name=document.source_file_name,
                similarity_score=round(similarity_score, 3),
                overlap_count=len(overlap),
                rationale_tags=rationale_tags,
                sample_titles=[item.title for item in candidate_obligations[:2]],
                open_escalations=open_escalations,
                pressure_level=pressure,
                recommended_focus=_recommended_focus(candidate_obligations),
            )
        )

    recommendations.sort(
        key=lambda item: (item.similarity_score, item.overlap_count, -item.open_escalations),
        reverse=True,
    )
    return recommendations[:5]


def _document_tokens(document: DocumentRecord, obligations: list[ObligationRecord]) -> set[str]:
    metadata = document.metadata if isinstance(document.metadata, dict) else {}
    cis = metadata.get("cis") if isinstance(metadata.get("cis"), dict) else {}
    parts = [
        document.source_file_name,
        _coerce_text(cis.get("court_name")),
        _coerce_text(cis.get("case_type")),
        _coerce_text(cis.get("bench")),
    ]

    department_tags = cis.get("department_tags")
    if isinstance(department_tags, list):
        parts.extend(str(item) for item in department_tags)

    for obligation in obligations:
        parts.append(obligation.title)
        parts.append(obligation.description or "")
        parts.append(obligation.owner_hint or "")

    tokens = set()
    for part in parts:
        if not part:
            continue
        for token in _TOKEN_PATTERN.findall(part.lower()):
            if token not in _SIMILARITY_STOPWORDS:
                tokens.add(token)

    return tokens


def _recommended_focus(obligations: list[ObligationRecord]) -> str:
    pending = sum(1 for item in obligations if item.review_state == "pending_review")
    open_escalations = sum(
        1 for item in obligations if bool(item.escalation and item.escalation.open)
    )
    if pending > 0:
        return "Compare how reviewers resolved similar obligations and owner assignments."
    if open_escalations > 0:
        return "Study how similar cases handled escalation, proof quality, and deadline recovery."
    return "Use the precedent for stronger obligation wording and execution notes."


def _coerce_text(value: object) -> str | None:
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    return None


def _related_cases_by_vector(
    *,
    active_document: DocumentRecord,
    active_obligations: list[ObligationRecord],
    documents: list[DocumentRecord],
    grouped_obligations: dict[UUID, list[ObligationRecord]],
) -> list[WorkbenchRelatedCase]:
    """pgvector-backed related-case search. Returns [] if unavailable."""
    if not active_obligations:
        return []
    try:
        from orderflow_api.core.clustering_service import find_similar_obligations
    except Exception:
        return []

    document_index = {document.id: document for document in documents}

    # Aggregate similarity per neighbouring document.
    per_document: dict[UUID, dict] = {}
    for active in active_obligations:
        try:
            neighbours = find_similar_obligations(active.id, k=20)
        except Exception:
            return []
        for neighbour in neighbours:
            if neighbour.document_id == active_document.id:
                continue
            entry = per_document.setdefault(
                neighbour.document_id,
                {"score_sum": 0.0, "matches": 0, "best_titles": set()},
            )
            entry["score_sum"] += neighbour.similarity
            entry["matches"] += 1
            entry["best_titles"].add(neighbour.title)

    if not per_document:
        return []

    recommendations: list[WorkbenchRelatedCase] = []
    for document_id, agg in per_document.items():
        document = document_index.get(document_id)
        if document is None:
            continue
        candidate_obligations = grouped_obligations.get(document_id, [])
        avg_similarity = agg["score_sum"] / max(1, agg["matches"])
        open_escalations = sum(
            1 for item in candidate_obligations if bool(item.escalation and item.escalation.open)
        )
        critical_escalations = sum(
            1
            for item in candidate_obligations
            if bool(
                item.escalation and item.escalation.open and item.escalation.level == "critical"
            )
        )
        pressure = (
            "critical"
            if critical_escalations > 0
            else "watch" if open_escalations > 0 else "stable"
        )
        rationale_tags = ["semantic-match", f"matches:{agg['matches']}"]

        recommendations.append(
            WorkbenchRelatedCase(
                document_id=document_id,
                source_file_name=document.source_file_name,
                similarity_score=round(avg_similarity, 3),
                overlap_count=agg["matches"],
                rationale_tags=rationale_tags,
                sample_titles=list(agg["best_titles"])[:2],
                open_escalations=open_escalations,
                pressure_level=pressure,
                recommended_focus=_recommended_focus(candidate_obligations),
            )
        )

    recommendations.sort(
        key=lambda item: (item.similarity_score, item.overlap_count, -item.open_escalations),
        reverse=True,
    )
    return recommendations[:5]
