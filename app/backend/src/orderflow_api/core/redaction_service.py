"""PII redaction for the Public-Trust read-only view (P1-4).

Goals:
- Strip personally identifying information (PII) from obligation text
  before exposing it on the public dashboard.
- Be conservative — when in doubt, redact.
- Preserve structural data: dates, monetary amounts, statute references,
  and obligation type. These help citizens understand the directive
  without identifying parties.

Implementation is regex + simple heuristics (no spaCy dependency required
to keep the install lean). Pattern coverage:
- Personal honorifics + names ("Shri/Smt./Dr./Mr./Ms./Justice/Hon'ble" + capitalized words)
- Phone numbers (Indian formats)
- Email addresses
- 12-digit Aadhaar-like numbers
- 10-character PAN-like alphanumerics (e.g. ABCDE1234F)
- Case numbers (W.P. 1234/2024 etc.)
- Specific addresses (door / plot / flat numbers)

The masking is deterministic so identical names get identical placeholders,
which keeps obligation text readable.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Iterable


# Honorifics that almost always precede a personal name in Indian legal docs.
_HONORIFICS = (
    r"(?:Shri|Smt\.?|Sri|Mr\.?|Mrs\.?|Ms\.?|Dr\.?|Justice|Hon'?ble|Hon\.?|Adv\.?|Advocate)"
)
_NAME_AFTER_HONORIFIC = re.compile(
    rf"\b{_HONORIFICS}\s+(?:[A-Z][a-zA-Z'\.]+(?:\s+[A-Z][a-zA-Z'\.]+){{0,3}})",
)

_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b", flags=re.IGNORECASE)
_PHONE = re.compile(
    r"\b(?:\+?91[-\s]?)?(?:\(?0?\d{2,4}\)?[-\s]?)?\d{6,10}\b"
)
_AADHAAR = re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b")
_PAN = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")
_CASE_NUMBER = re.compile(
    r"\b(?:W\.?P\.?|S\.?L\.?P\.?|C\.?A\.?|Crl\.?|Crl\.?A\.?|Civil Appeal|Writ Petition)"
    r"\s*(?:\(C\)|\(Civil\)|\(Crl\.?\))?\s*(?:No\.?\s*)?\d+(?:[/\-]\d{2,4})?",
    flags=re.IGNORECASE,
)
_ADDRESS_HINTS = re.compile(
    r"\b(?:Plot|Flat|Door|House|Building)\s*(?:No\.?)?\s*[A-Z0-9/\-]+",
    flags=re.IGNORECASE,
)

# A small whitelist of generic capitalized terms we should NEVER mask, even
# if they appear after an honorific by accident.
_NAME_WHITELIST = {
    "court",
    "department",
    "government",
    "state",
    "union",
    "india",
    "ministry",
    "secretariat",
    "commission",
    "tribunal",
    "petitioner",
    "respondent",
    "appellant",
    "applicant",
    "judge",
    "judges",
    "bench",
}


@dataclass
class RedactionStats:
    names: int = 0
    emails: int = 0
    phones: int = 0
    aadhaar: int = 0
    pan: int = 0
    case_numbers: int = 0
    addresses: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "names": self.names,
            "emails": self.emails,
            "phones": self.phones,
            "aadhaar": self.aadhaar,
            "pan": self.pan,
            "case_numbers": self.case_numbers,
            "addresses": self.addresses,
            "total": (
                self.names + self.emails + self.phones + self.aadhaar
                + self.pan + self.case_numbers + self.addresses
            ),
        }


def _stable_token(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.lower().encode("utf-8")).hexdigest()[:6]
    return f"[{prefix}-{digest}]"


def _maybe_redact_name(match: re.Match) -> str:
    full = match.group(0)
    # Inspect the trailing word(s) — if they are whitelisted generic terms,
    # leave the phrase alone to avoid masking "Hon'ble Court" → "[NAME]".
    trailing = full.split()[1:]
    if any(word.strip(".,;").lower() in _NAME_WHITELIST for word in trailing):
        return full
    return _stable_token("PERSON", full)


def redact_text(text: str | None) -> tuple[str, RedactionStats]:
    """Mask PII in a single string. Returns (redacted, stats)."""
    stats = RedactionStats()
    if not text:
        return "", stats

    redacted = text

    # Aadhaar / PAN must run before generic phone matcher so they don't
    # get swallowed.
    def _aadhaar_repl(m: re.Match) -> str:
        stats.aadhaar += 1
        return _stable_token("AADHAAR", m.group(0))

    redacted = _AADHAAR.sub(_aadhaar_repl, redacted)

    def _pan_repl(m: re.Match) -> str:
        stats.pan += 1
        return _stable_token("PAN", m.group(0))

    redacted = _PAN.sub(_pan_repl, redacted)

    def _email_repl(m: re.Match) -> str:
        stats.emails += 1
        return _stable_token("EMAIL", m.group(0))

    redacted = _EMAIL.sub(_email_repl, redacted)

    def _phone_repl(m: re.Match) -> str:
        # Skip pure 4-digit years (2024 etc.) which would otherwise match
        # the lower bound of the phone regex.
        raw = m.group(0)
        digits = re.sub(r"\D", "", raw)
        if len(digits) <= 4:
            return raw
        stats.phones += 1
        return _stable_token("PHONE", raw)

    redacted = _PHONE.sub(_phone_repl, redacted)

    def _case_repl(m: re.Match) -> str:
        stats.case_numbers += 1
        return _stable_token("CASE", m.group(0))

    redacted = _CASE_NUMBER.sub(_case_repl, redacted)

    def _addr_repl(m: re.Match) -> str:
        stats.addresses += 1
        return _stable_token("ADDR", m.group(0))

    redacted = _ADDRESS_HINTS.sub(_addr_repl, redacted)

    def _name_repl(m: re.Match) -> str:
        replacement = _maybe_redact_name(m)
        if replacement != m.group(0):
            stats.names += 1
        return replacement

    redacted = _NAME_AFTER_HONORIFIC.sub(_name_repl, redacted)

    return redacted, stats


def redact_obligation(obligation, *, mask_owner: bool = True) -> dict:
    """Return a dict projection of an obligation with PII masked.

    Only the public-safe fields are returned — internal owner emails,
    audit details, and citations stay server-side.
    """
    title, t_stats = redact_text(getattr(obligation, "title", "") or "")
    description, d_stats = redact_text(getattr(obligation, "description", "") or "")

    owner = getattr(obligation, "owner_hint", None)
    if owner and mask_owner:
        owner_redacted, _ = redact_text(owner)
    else:
        owner_redacted = owner if owner else None

    risk_score = getattr(obligation, "risk_score", None)
    risk_band = getattr(obligation, "risk_band", None)

    redacted_counts = {
        key: t_stats.to_dict()[key] + d_stats.to_dict()[key]
        for key in t_stats.to_dict().keys()
    }

    return {
        "id": str(getattr(obligation, "id", "")),
        "document_id": str(getattr(obligation, "document_id", "")),
        "title": title,
        "description": description,
        "owner_role": owner_redacted,
        "due_date": getattr(obligation, "due_date", None).isoformat()
        if getattr(obligation, "due_date", None) is not None
        else None,
        "status": getattr(obligation, "status", None),
        "priority": getattr(obligation, "priority", None),
        "review_state": getattr(obligation, "review_state", None),
        "risk_score": risk_score,
        "risk_band": risk_band,
        "redaction": redacted_counts,
    }


def redact_obligations(items: Iterable) -> list[dict]:
    return [redact_obligation(o) for o in items]
