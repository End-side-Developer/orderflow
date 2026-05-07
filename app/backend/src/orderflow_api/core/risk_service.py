"""Contempt-Risk scoring (P0-1).

Produces an explainable 0-100 risk score per obligation, plus the top
contributing factors so the UI can render a "why this score?" breakdown.

Pure function — no I/O — so it can be unit-tested in isolation and
applied to any `ObligationRecord` regardless of source (stub or persisted).

Scoring is a weighted sum of normalized factor contributions:

    score = sum(weight_i * value_i)  capped to [0, 100]

Factors:
- deadline_pressure  — closer / past due  ⇒ higher
- proof_gap          — no annotations / unverified evidence  ⇒ higher
- review_status      — pending review or rejected  ⇒ higher
- priority_weight    — high / critical priority  ⇒ higher
- owner_workload     — same owner has many open obligations  ⇒ higher
- dependency_depth   — flagged blocked obligations  ⇒ higher
- escalation_history — currently flagged at watch / escalated / critical
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Iterable


@dataclass
class RiskFactor:
    name: str
    weight: float  # weight applied to this factor (0..1)
    contribution: float  # weight * normalized value, in score points
    detail: str  # human-readable explanation


@dataclass
class ContemptRiskScore:
    score: int  # 0..100
    band: str  # low | moderate | high | critical
    factors: list[RiskFactor]  # all factors, ordered by contribution desc
    top_factors: list[RiskFactor]  # top-3 cut


_FACTOR_WEIGHTS = {
    "deadline_pressure": 30.0,
    "proof_gap": 20.0,
    "review_status": 15.0,
    "priority_weight": 12.0,
    "owner_workload": 10.0,
    "dependency_depth": 8.0,
    "escalation_history": 5.0,
}

_PRIORITY_VALUE = {
    "low": 0.1,
    "medium": 0.4,
    "high": 0.75,
    "critical": 1.0,
}

_ESCALATION_VALUE = {
    "none": 0.0,
    "watch": 0.4,
    "escalated": 0.75,
    "critical": 1.0,
}


def _band(score: int) -> str:
    if score >= 75:
        return "critical"
    if score >= 50:
        return "high"
    if score >= 25:
        return "moderate"
    return "low"


def _deadline_pressure_value(due_date: date | None) -> tuple[float, str]:
    """Returns (normalized 0..1, explanation)."""
    if due_date is None:
        return 0.3, "No deadline recorded — uncertainty inflates pressure."
    today = datetime.now(timezone.utc).date()
    days_left = (due_date - today).days
    if days_left < 0:
        # Past due — saturate.
        return 1.0, f"Overdue by {abs(days_left)} day(s)."
    if days_left == 0:
        return 1.0, "Deadline is today."
    if days_left <= 3:
        return 0.95, f"Only {days_left} day(s) until deadline."
    if days_left <= 7:
        return 0.8, f"{days_left} days remaining — within one-week window."
    if days_left <= 14:
        return 0.6, f"{days_left} days remaining — entering the two-week pressure zone."
    if days_left <= 30:
        return 0.4, f"{days_left} days remaining — early warning."
    if days_left <= 60:
        return 0.2, f"{days_left} days remaining — comfortable buffer."
    return 0.05, f"{days_left} days remaining — far from deadline."


def _proof_gap_value(obligation, proof_attached: bool | None) -> tuple[float, str]:
    if obligation.status == "completed":
        return 0.0, "Obligation already closed with verified proof."
    if proof_attached is True:
        return 0.2, "Proof annotations attached but not yet verified."
    if proof_attached is False:
        return 0.95, "No proof or evidence has been attached."
    # Unknown — treat as gap.
    return 0.7, "Proof status unknown — assume evidence missing."


def _review_status_value(obligation) -> tuple[float, str]:
    state = obligation.review_state
    status = obligation.status
    if status == "rejected" or state == "rejected":
        return 1.0, "Obligation rejected during review — execution at risk."
    if state == "pending_review":
        return 0.7, "Awaiting reviewer approval before execution can begin."
    if status == "completed":
        return 0.0, "Obligation completed."
    if state == "approved":
        return 0.1, "Reviewer-approved and in execution."
    return 0.3, "Review state unclassified."


def _priority_value(obligation) -> tuple[float, str]:
    priority = obligation.priority or "medium"
    val = _PRIORITY_VALUE.get(priority, 0.4)
    return val, f"Priority `{priority}` contributes {val:.2f}."


def _owner_workload_value(obligation, owner_open_counts: dict[str, int]) -> tuple[float, str]:
    owner = (obligation.owner_hint or "").strip().lower()
    if not owner:
        return 0.5, "Owner unassigned — risk of dropped accountability."
    count = owner_open_counts.get(owner, 0)
    if count <= 1:
        return 0.05, f"Owner has {count} open obligation."
    if count <= 3:
        return 0.3, f"Owner managing {count} open obligations."
    if count <= 6:
        return 0.6, f"Owner overloaded with {count} open obligations."
    return 0.9, f"Owner saturated with {count} open obligations — execution bottleneck likely."


def _dependency_depth_value(obligation) -> tuple[float, str]:
    """Approximation — we don't have an explicit dep graph yet."""
    escalation = obligation.escalation
    if escalation and escalation.reasons:
        blocked_terms = ("blocked", "dependency", "waiting", "prerequisite")
        for reason in escalation.reasons:
            text = (reason or "").lower()
            if any(t in text for t in blocked_terms):
                return 0.85, f"Blocked by upstream item: {reason}"
    return 0.1, "No upstream dependency blockers detected."


def _escalation_history_value(obligation) -> tuple[float, str]:
    escalation = obligation.escalation
    if escalation is None:
        return 0.0, "No escalation signal."
    val = _ESCALATION_VALUE.get(escalation.level, 0.0)
    if escalation.open:
        return val, f"Escalation flagged `{escalation.level}` and currently open."
    return val * 0.4, f"Escalation `{escalation.level}` previously raised."


def _build_owner_workload_index(all_obligations: Iterable) -> dict[str, int]:
    counts: dict[str, int] = {}
    for o in all_obligations:
        if o.status == "completed":
            continue
        owner = (o.owner_hint or "").strip().lower()
        if not owner:
            continue
        counts[owner] = counts.get(owner, 0) + 1
    return counts


def compute_contempt_risk(
    obligation,
    *,
    owner_open_counts: dict[str, int] | None = None,
    proof_attached: bool | None = None,
) -> ContemptRiskScore:
    """Compute the explainable 0-100 risk score for a single obligation.

    `owner_open_counts` is an optional precomputed map of owner → open
    obligation count, allowing batch scoring to skip recomputing it per
    obligation. When None, the workload factor uses 0 (single-record mode).
    """
    workload = owner_open_counts or {}

    factor_inputs = [
        ("deadline_pressure", *_deadline_pressure_value(obligation.due_date)),
        ("proof_gap", *_proof_gap_value(obligation, proof_attached)),
        ("review_status", *_review_status_value(obligation)),
        ("priority_weight", *_priority_value(obligation)),
        ("owner_workload", *_owner_workload_value(obligation, workload)),
        ("dependency_depth", *_dependency_depth_value(obligation)),
        ("escalation_history", *_escalation_history_value(obligation)),
    ]

    factors: list[RiskFactor] = []
    total = 0.0
    for name, value, detail in factor_inputs:
        weight = _FACTOR_WEIGHTS[name]
        contribution = weight * max(0.0, min(1.0, value))
        total += contribution
        factors.append(
            RiskFactor(
                name=name,
                weight=weight,
                contribution=round(contribution, 2),
                detail=detail,
            )
        )

    score = int(round(max(0.0, min(100.0, total))))
    factors.sort(key=lambda f: f.contribution, reverse=True)
    top = factors[:3]
    return ContemptRiskScore(
        score=score,
        band=_band(score),
        factors=factors,
        top_factors=top,
    )


def annotate_obligations_with_risk(obligations: list) -> None:
    """In-place: attach `risk_score` + `risk_factors` dicts to each item.

    Designed to operate on Pydantic models OR plain objects. Modifies the
    object's `__dict__` for Pydantic v2 models via `model_copy`-friendly
    attribute write where possible. For loose duck-typed structures we
    just set attributes.
    """
    workload = _build_owner_workload_index(obligations)
    for obligation in obligations:
        result = compute_contempt_risk(obligation, owner_open_counts=workload)
        risk_payload = {
            "score": result.score,
            "band": result.band,
            "top_factors": [
                {
                    "name": f.name,
                    "weight": f.weight,
                    "contribution": f.contribution,
                    "detail": f.detail,
                }
                for f in result.top_factors
            ],
            "factors": [
                {
                    "name": f.name,
                    "weight": f.weight,
                    "contribution": f.contribution,
                    "detail": f.detail,
                }
                for f in result.factors
            ],
        }
        try:
            object.__setattr__(obligation, "risk_score", result.score)
            object.__setattr__(obligation, "risk_band", result.band)
            object.__setattr__(obligation, "risk_factors", risk_payload["top_factors"])
            object.__setattr__(obligation, "risk_factors_full", risk_payload["factors"])
        except Exception:
            # Pydantic v2 models with extra="forbid" will refuse — caller
            # is expected to have schema fields. We silently skip in that
            # case rather than crash.
            pass
