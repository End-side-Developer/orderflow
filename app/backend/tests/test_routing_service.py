"""Tests for the Department-Aware Routing service (P1-1)."""

from __future__ import annotations

from orderflow_api.core.routing_service import route_directive


def test_routes_revenue_directive() -> None:
    decision = route_directive(
        "The Tehsildar shall update land records and serve a copy to the "
        "Collector within 30 days."
    )
    assert decision.primary is not None
    assert decision.primary.code == "REVENUE"
    assert decision.primary.confidence >= 0.5
    assert decision.suggested_officers, "expected officers for revenue"


def test_routes_health_directive() -> None:
    decision = route_directive(
        "The Chief Medical Officer is directed to ensure that the primary "
        "health centre maintains adequate medicine stock."
    )
    assert decision.primary is not None
    assert decision.primary.code == "HEALTH"


def test_flags_multi_department_directive() -> None:
    decision = route_directive(
        "The Municipal Corporation in coordination with the Public Works "
        "Department shall lay roads and ensure water supply through the "
        "Public Health Engineering wing."
    )
    assert decision.multi_department is True
    codes = {c.code for c in decision.candidates}
    assert "URBAN_DEV" in codes
    assert "PWD" in codes or "WATER" in codes


def test_returns_empty_when_no_match() -> None:
    decision = route_directive(
        "The party shall behave decorously and not interrupt the proceedings."
    )
    assert decision.primary is None
    assert decision.suggested_officers == []


def test_empty_text_does_not_crash() -> None:
    decision = route_directive("")
    assert decision.primary is None
    assert decision.candidates == []
