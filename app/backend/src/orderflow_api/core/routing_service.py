"""Department-Aware Routing (P1-1).

Maps free-text directives from court judgments to canonical Indian
government departments and proposes specific officers from a sample
directory. The data files live alongside this service so routing
decisions are reproducible and auditable.

The matcher is intentionally simple — keyword + alias scoring — so it
runs fast at extraction time and always produces a top-N candidate list
with confidence. Replace the underlying directory before production;
the matcher itself stays.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_DEPARTMENT_FILE = _DATA_DIR / "canonical_departments.json"
_OFFICER_FILE = _DATA_DIR / "officer_directory.json"


@dataclass
class DepartmentMatch:
    code: str
    name: str
    confidence: float           # 0..1
    matched_aliases: list[str]


@dataclass
class OfficerSuggestion:
    id: str
    name: str
    designation: str
    department_code: str
    jurisdiction: str
    contact: str


@dataclass
class RoutingDecision:
    primary: DepartmentMatch | None
    candidates: list[DepartmentMatch]
    suggested_officers: list[OfficerSuggestion]
    multi_department: bool   # true when 2+ departments scored above threshold
    rationale: str


@lru_cache(maxsize=1)
def _load_departments() -> list[dict]:
    if not _DEPARTMENT_FILE.exists():
        logger.warning("canonical_departments.json missing at %s", _DEPARTMENT_FILE)
        return []
    try:
        return json.loads(_DEPARTMENT_FILE.read_text(encoding="utf-8")).get(
            "departments", []
        )
    except Exception as exc:
        logger.error("Failed to read canonical departments: %s", exc)
        return []


@lru_cache(maxsize=1)
def _load_officers() -> list[dict]:
    if not _OFFICER_FILE.exists():
        logger.warning("officer_directory.json missing at %s", _OFFICER_FILE)
        return []
    try:
        return json.loads(_OFFICER_FILE.read_text(encoding="utf-8")).get(
            "officers", []
        )
    except Exception as exc:
        logger.error("Failed to read officer directory: %s", exc)
        return []


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower().strip())


def _score_department(text: str, department: dict) -> tuple[float, list[str]]:
    """Score 0..1 + the aliases that matched."""
    matched: list[str] = []
    name = department.get("name", "")
    code = department.get("code", "")
    aliases = department.get("aliases", []) or []

    # Each alias is checked as a whole-word substring.
    for alias in [name, code, *aliases]:
        if not alias:
            continue
        token = alias.lower().strip()
        if not token:
            continue
        # Use word-boundary matching so "labour" doesn't match inside "labourers"
        # but "labour commissioner" still hits via the full alias.
        pattern = r"\b" + re.escape(token) + r"\b"
        if re.search(pattern, text):
            matched.append(alias)

    if not matched:
        return 0.0, []

    # Confidence ramps with the number of distinct aliases hit, capped at 1.0.
    # Two hits is a strong signal; three or more saturates.
    score = min(1.0, 0.5 + 0.25 * (len(set(a.lower() for a in matched)) - 1))
    return score, matched


def route_directive(
    text: str,
    *,
    top_n_candidates: int = 3,
    top_officers_per_department: int = 2,
    confidence_threshold: float = 0.5,
) -> RoutingDecision:
    """Route a directive's text to the most likely department(s) + officers.

    `text` is the obligation title + description (the caller decides what
    to feed). Returns a RoutingDecision with rationale text suitable for
    display in the review UI.
    """
    normalized = _normalize(text)
    if not normalized:
        return RoutingDecision(
            primary=None,
            candidates=[],
            suggested_officers=[],
            multi_department=False,
            rationale="No text provided to route.",
        )

    departments = _load_departments()
    scored: list[DepartmentMatch] = []
    for dept in departments:
        score, matched = _score_department(normalized, dept)
        if score >= confidence_threshold:
            scored.append(
                DepartmentMatch(
                    code=dept.get("code", ""),
                    name=dept.get("name", ""),
                    confidence=score,
                    matched_aliases=matched,
                )
            )

    scored.sort(key=lambda m: m.confidence, reverse=True)
    candidates = scored[:top_n_candidates]
    primary = candidates[0] if candidates else None

    multi_department = len(scored) >= 2

    officers: list[OfficerSuggestion] = []
    if primary is not None:
        all_officers = _load_officers()
        primary_officers = [
            OfficerSuggestion(
                id=o["id"],
                name=o["name"],
                designation=o["designation"],
                department_code=o["department_code"],
                jurisdiction=o["jurisdiction"],
                contact=o["contact"],
            )
            for o in all_officers
            if o.get("department_code") == primary.code
        ]
        officers = primary_officers[:top_officers_per_department]

    rationale = _build_rationale(primary, candidates, multi_department)

    return RoutingDecision(
        primary=primary,
        candidates=candidates,
        suggested_officers=officers,
        multi_department=multi_department,
        rationale=rationale,
    )


def _build_rationale(
    primary: DepartmentMatch | None,
    candidates: list[DepartmentMatch],
    multi_department: bool,
) -> str:
    if primary is None:
        return (
            "No canonical department matched the directive. Reviewer should "
            "tag department manually or expand the alias dictionary."
        )

    lead = (
        f"Routed to {primary.name} ({primary.code}) at "
        f"confidence {primary.confidence:.2f} via "
        f"{', '.join(primary.matched_aliases[:3])}."
    )
    if multi_department and len(candidates) > 1:
        secondary_names = ", ".join(c.name for c in candidates[1:])
        lead += (
            f" Multi-department obligation flagged — also touches: "
            f"{secondary_names}. Consider explicit hand-off in execution plan."
        )
    return lead
