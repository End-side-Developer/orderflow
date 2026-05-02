"""Tests for the Contempt-Risk scoring service (P0-1)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

from orderflow_api.core.risk_service import (
    annotate_obligations_with_risk,
    compute_contempt_risk,
)


@dataclass
class _Escalation:
    level: str = "none"
    open: bool = False
    reasons: list[str] | None = None
    days_until_due: int | None = None


@dataclass
class _Ob:
    id: str
    title: str
    description: str | None = None
    owner_hint: str | None = None
    due_date: date | None = None
    status: str = "active"
    priority: str = "medium"
    review_state: str = "pending_review"
    escalation: Any = None
    created_at: datetime | None = None


def _today() -> date:
    return datetime.now(timezone.utc).date()


def test_score_in_range_0_to_100() -> None:
    ob = _Ob(
        id="x",
        title="Submit report",
        due_date=_today() + timedelta(days=14),
        priority="medium",
        review_state="pending_review",
        escalation=_Escalation(level="none", open=False),
    )
    result = compute_contempt_risk(ob)
    assert 0 <= result.score <= 100
    assert result.band in {"low", "moderate", "high", "critical"}


def test_overdue_obligation_scores_higher_than_distant_one() -> None:
    overdue = _Ob(
        id="overdue",
        title="Pay arrears",
        due_date=_today() - timedelta(days=10),
        priority="high",
        review_state="approved",
        status="active",
        escalation=_Escalation(level="critical", open=True),
    )
    distant = _Ob(
        id="distant",
        title="Pay arrears",
        due_date=_today() + timedelta(days=120),
        priority="medium",
        review_state="approved",
        status="active",
        escalation=_Escalation(level="none", open=False),
    )

    overdue_score = compute_contempt_risk(overdue).score
    distant_score = compute_contempt_risk(distant).score
    assert overdue_score > distant_score


def test_completed_obligation_proof_factor_drops() -> None:
    # Completed status should kill the proof_gap contribution.
    completed = _Ob(
        id="done",
        title="Submit report",
        due_date=_today() - timedelta(days=2),
        priority="high",
        review_state="approved",
        status="completed",
        escalation=_Escalation(level="none", open=False),
    )
    result = compute_contempt_risk(completed)
    proof_gap = next(f for f in result.factors if f.name == "proof_gap")
    assert proof_gap.contribution == 0.0


def test_top_factors_returns_three_items() -> None:
    ob = _Ob(
        id="x",
        title="Submit report",
        due_date=_today() + timedelta(days=2),
        priority="critical",
        review_state="pending_review",
        escalation=_Escalation(level="critical", open=True, reasons=["blocked by upstream item"]),
    )
    result = compute_contempt_risk(ob)
    assert len(result.top_factors) == 3
    # Top factor's contribution should be ≥ the others.
    assert result.top_factors[0].contribution >= result.top_factors[1].contribution
    assert result.top_factors[1].contribution >= result.top_factors[2].contribution


def test_owner_workload_factor_responds_to_count() -> None:
    light = _Ob(
        id="x",
        title="t",
        owner_hint="Alice",
        due_date=_today() + timedelta(days=30),
        priority="medium",
        review_state="approved",
        escalation=_Escalation(),
    )
    heavy = _Ob(
        id="y",
        title="t",
        owner_hint="Alice",
        due_date=_today() + timedelta(days=30),
        priority="medium",
        review_state="approved",
        escalation=_Escalation(),
    )
    workload = {"alice": 8}
    light_factor = next(
        f
        for f in compute_contempt_risk(light, owner_open_counts={"alice": 1}).factors
        if f.name == "owner_workload"
    )
    heavy_factor = next(
        f
        for f in compute_contempt_risk(heavy, owner_open_counts=workload).factors
        if f.name == "owner_workload"
    )
    assert heavy_factor.contribution > light_factor.contribution


def test_annotate_obligations_with_risk_attaches_fields() -> None:
    items = [
        _Ob(
            id="a",
            title="x",
            due_date=_today() + timedelta(days=2),
            priority="critical",
            review_state="pending_review",
            escalation=_Escalation(level="critical", open=True),
        ),
        _Ob(
            id="b",
            title="y",
            due_date=_today() + timedelta(days=120),
            priority="low",
            review_state="approved",
            status="completed",
            escalation=_Escalation(),
        ),
    ]
    annotate_obligations_with_risk(items)
    assert items[0].risk_score > items[1].risk_score
    assert items[0].risk_band in {"low", "moderate", "high", "critical"}
    assert len(items[0].risk_factors) == 3
