"""Department Health Scoring (P1-2).

Aggregates obligations by department and emits a 0-100 health score
along with the underlying metrics. The score rewards on-time completion
and penalizes breach rate, escalations, and average risk score.

Departments are derived from:
1. Document metadata `additional_metadata.department` (free text), then
2. The routing service's classifier applied to the document's first
   obligation when metadata is absent.

The score model:
    health = 100
           - 35 * breach_rate
           - 20 * (avg_risk / 100)
           - 25 * critical_escalation_rate
           - 20 * pending_review_rate
           + 0  (capped to 0..100)

Bands:  excellent ≥ 80, healthy ≥ 60, watch ≥ 40, at_risk < 40.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Iterable

from orderflow_api.core.routing_service import route_directive


@dataclass
class DepartmentHealthRecord:
    code: str
    name: str
    total_obligations: int
    completed: int
    overdue: int
    pending_review: int
    open_escalations: int
    critical_escalations: int
    avg_risk_score: float
    compliance_rate: float          # completed / total
    breach_rate: float              # overdue / total
    health_score: int               # 0..100
    band: str                       # excellent / healthy / watch / at_risk
    rationale: list[str]


def _today_utc() -> date:
    return datetime.now(timezone.utc).date()


def _is_overdue(obligation) -> bool:
    if obligation.status == "completed":
        return False
    if obligation.due_date is None:
        return False
    return obligation.due_date < _today_utc()


def _safe_ratio(numerator: int, denominator: int) -> float:
    return (numerator / denominator) if denominator > 0 else 0.0


def _band(score: int) -> str:
    if score >= 80:
        return "excellent"
    if score >= 60:
        return "healthy"
    if score >= 40:
        return "watch"
    return "at_risk"


def _resolve_department(document, obligations: list) -> tuple[str, str]:
    """Returns (code, display_name) for a document.

    Resolution order (uses the first signal that yields a primary match):
    1. metadata.department (top-level — set by generic upload form)
    2. metadata.additional_metadata.department (set when explicitly nested)
    3. metadata.cis.department_tags (list — set by eCourts intake adapter)
    4. metadata.cis.bench / metadata.cis.case_type (last-ditch hint)
    5. Routing classifier on first obligations
    6. ('UNCLASSIFIED', 'Unclassified')
    """
    metadata = getattr(document, "metadata", None) or {}
    if not isinstance(metadata, dict):
        metadata = {}

    candidate_texts: list[str] = []

    top_level = metadata.get("department")
    if isinstance(top_level, str) and top_level.strip():
        candidate_texts.append(top_level)

    additional = metadata.get("additional_metadata")
    if isinstance(additional, dict):
        nested = additional.get("department")
        if isinstance(nested, str) and nested.strip():
            candidate_texts.append(nested)

    cis = metadata.get("cis")
    if isinstance(cis, dict):
        tags = cis.get("department_tags")
        if isinstance(tags, list):
            candidate_texts.extend(str(t) for t in tags if t)
        for hint_key in ("bench", "case_type", "court_name"):
            value = cis.get(hint_key)
            if isinstance(value, str) and value.strip():
                candidate_texts.append(value)

    for text in candidate_texts:
        decision = route_directive(text)
        if decision.primary is not None:
            return decision.primary.code, decision.primary.name

    if obligations:
        sample_text = " ".join(
            (o.title or "") + " " + (o.description or "") for o in obligations[:3]
        )
        decision = route_directive(sample_text)
        if decision.primary is not None:
            return decision.primary.code, decision.primary.name

    # Final fallback: if free-text was supplied but didn't classify, surface
    # the user's own label rather than a generic "Unclassified" bucket.
    if candidate_texts:
        label = candidate_texts[0].strip()[:60]
        if label:
            return f"USER:{label.upper()}", label

    return "UNCLASSIFIED", "Unclassified"


def compute_department_health(
    documents: Iterable,
    obligations_by_doc: dict,
    *,
    obligations_with_risk: list | None = None,
) -> list[DepartmentHealthRecord]:
    """Build per-department health records.

    Inputs:
    - `documents`: list of DocumentRecord-like objects.
    - `obligations_by_doc`: {document_id: [ObligationRecord, ...]}.
    - `obligations_with_risk`: optional flat list of obligations that have
      already been annotated with `risk_score`. When None, risk = 0.
    """
    risk_index: dict = {}
    if obligations_with_risk:
        for o in obligations_with_risk:
            score = getattr(o, "risk_score", None)
            if score is not None:
                risk_index[o.id] = score

    grouped: dict[str, dict] = defaultdict(
        lambda: {
            "name": "",
            "obligations": [],
        }
    )

    for document in documents:
        document_obligations = obligations_by_doc.get(document.id, [])
        code, name = _resolve_department(document, document_obligations)
        bucket = grouped[code]
        bucket["name"] = name
        bucket["obligations"].extend(document_obligations)

    records: list[DepartmentHealthRecord] = []
    for code, bucket in grouped.items():
        obligations = bucket["obligations"]
        total = len(obligations)
        if total == 0:
            continue

        completed = sum(1 for o in obligations if o.status == "completed")
        overdue = sum(1 for o in obligations if _is_overdue(o))
        pending_review = sum(1 for o in obligations if o.review_state == "pending_review")
        open_escalations = sum(
            1 for o in obligations if bool(o.escalation and o.escalation.open)
        )
        critical_escalations = sum(
            1
            for o in obligations
            if bool(
                o.escalation and o.escalation.open and o.escalation.level == "critical"
            )
        )

        risk_values = [
            risk_index.get(o.id) for o in obligations if risk_index.get(o.id) is not None
        ]
        avg_risk = sum(risk_values) / len(risk_values) if risk_values else 0.0

        compliance_rate = _safe_ratio(completed, total)
        breach_rate = _safe_ratio(overdue, total)
        critical_rate = _safe_ratio(critical_escalations, total)
        review_rate = _safe_ratio(pending_review, total)

        score_float = (
            100.0
            - 35.0 * breach_rate
            - 20.0 * (avg_risk / 100.0)
            - 25.0 * critical_rate
            - 20.0 * review_rate
        )
        score = int(round(max(0.0, min(100.0, score_float))))
        band = _band(score)

        rationale: list[str] = []
        if breach_rate > 0:
            rationale.append(
                f"Breach rate {breach_rate * 100:.0f}% drags score by "
                f"{35 * breach_rate:.1f} pts."
            )
        if avg_risk > 0:
            rationale.append(
                f"Average contempt-risk {avg_risk:.0f}/100 across open items."
            )
        if critical_rate > 0:
            rationale.append(
                f"Critical escalations {critical_rate * 100:.0f}% of portfolio."
            )
        if review_rate > 0:
            rationale.append(
                f"Pending-review backlog {review_rate * 100:.0f}% of portfolio."
            )
        if not rationale:
            rationale.append("Department is in good standing — no negative signals.")

        records.append(
            DepartmentHealthRecord(
                code=code,
                name=bucket["name"] or code,
                total_obligations=total,
                completed=completed,
                overdue=overdue,
                pending_review=pending_review,
                open_escalations=open_escalations,
                critical_escalations=critical_escalations,
                avg_risk_score=round(avg_risk, 1),
                compliance_rate=round(compliance_rate, 3),
                breach_rate=round(breach_rate, 3),
                health_score=score,
                band=band,
                rationale=rationale,
            )
        )

    records.sort(key=lambda r: r.health_score)  # worst-first → action priority
    return records
