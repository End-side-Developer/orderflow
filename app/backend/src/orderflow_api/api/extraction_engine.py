from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import importlib
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from typing import Any
from uuid import UUID, uuid4

_DIRECTIVE_PATTERN = re.compile(
    r"\b(shall|must|is directed to|are directed to|is ordered to|are ordered to)\b",
    re.IGNORECASE,
)
_DIRECTIVE_SPLIT_PATTERN = re.compile(
    r"\b(?:shall|must|is directed to|are directed to|is ordered to|are ordered to)\b",
    re.IGNORECASE,
)
_DUE_DAYS_PATTERN = re.compile(r"\b(?:within|in)\s+(\d{1,3})\s+day(?:s)?\b", re.IGNORECASE)
_EXPLICIT_DATE_PATTERN = re.compile(
    (
        r"\b(?:by|on|before)\s+(?P<value>"
        r"(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4})|"
        r"(?:\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})"
        r")\b"
    ),
    re.IGNORECASE,
)
_TEMPORAL_HINT_PATTERN = re.compile(
    r"\b(before\s+next\s+\w+|at\s+the\s+earliest|forthwith|immediately)\b",
    re.IGNORECASE,
)
_PDF_CONTENT_TYPE = "application/pdf"
_NATURAL_LANGUAGE_HINTS = {
    "the",
    "and",
    "shall",
    "must",
    "is",
    "are",
    "within",
    "days",
    "court",
    "order",
    "judgment",
    "compliance",
}
# Unicode ranges for Indic scripts used by OrderFlow's supported languages
# (hi/mr → Devanagari, ta → Tamil, te → Telugu, kn → Kannada, ml → Malayalam).
# Detecting any of these lets us accept text that pypdf extracted from a
# regional-language PDF, which the English-only heuristics would otherwise
# discard.
_INDIC_SCRIPT_RANGES: tuple[tuple[int, int], ...] = (
    (0x0900, 0x097F),  # Devanagari (Hindi, Marathi)
    (0x0B80, 0x0BFF),  # Tamil
    (0x0C00, 0x0C7F),  # Telugu
    (0x0C80, 0x0CFF),  # Kannada
    (0x0D00, 0x0D7F),  # Malayalam
)


@dataclass(frozen=True)
class ParsedClause:
    id: UUID
    document_id: UUID
    clause_index: int
    page_number: int | None
    span_start: int | None
    span_end: int | None
    text: str
    normalized_text: str
    confidence: float


@dataclass(frozen=True)
class ParsedObligation:
    id: UUID
    document_id: UUID
    clause_id: UUID | None
    obligation_code: str
    title: str
    description: str
    owner_hint: str | None
    due_date: date | None
    status: str
    priority: str
    review_state: str
    confidence: float
    citation_page_number: int | None
    citation_clause_span: str
    metadata: dict[str, object]


@dataclass(frozen=True)
class StructuredObligationFields:
    owner_hint: str | None
    action_phrase: str | None
    due_days: int | None
    due_date: date | None
    deadline_source: str | None
    temporal_hint: str | None


def decode_document_text(
    payload: bytes,
    content_type: str | None,
    source_file_name: str | None = None,
) -> str:
    if not payload:
        raise ValueError("Document payload is empty")

    normalized_type = (content_type or "").lower()
    if normalized_type.startswith("text/") or normalized_type in {
        "application/json",
        "application/xml",
    }:
        text = payload.decode("utf-8", errors="replace")
        return _normalize_document_text(text)

    if _is_pdf_document(normalized_type, source_file_name):
        return _decode_pdf_text(payload, source_file_name)

    text = payload.decode("utf-8", errors="replace")
    if not _is_mostly_printable(text):
        raise ValueError(
            "Phase B extraction currently supports text-readable documents only; "
            "upload a text file for now."
        )

    return _normalize_document_text(text)


def segment_clauses(raw_text: str, document_id: UUID) -> list[ParsedClause]:
    clauses: list[ParsedClause] = []
    clause_index = 1

    for page_number, page_text, page_offset in _iter_pages(raw_text):
        for chunk, span_start, span_end in _iter_clause_chunks(page_text, page_offset):
            normalized = _normalize_whitespace(chunk)
            if not normalized:
                continue

            confidence = 0.86 if _DIRECTIVE_PATTERN.search(normalized) else 0.68
            clauses.append(
                ParsedClause(
                    id=uuid4(),
                    document_id=document_id,
                    clause_index=clause_index,
                    page_number=page_number,
                    span_start=span_start,
                    span_end=span_end,
                    text=chunk.strip(),
                    normalized_text=normalized,
                    confidence=round(confidence, 2),
                )
            )
            clause_index += 1

    if clauses:
        return clauses

    fallback = _normalize_whitespace(raw_text)
    if not fallback:
        return []

    return [
        ParsedClause(
            id=uuid4(),
            document_id=document_id,
            clause_index=1,
            page_number=1,
            span_start=0,
            span_end=len(raw_text),
            text=fallback,
            normalized_text=fallback,
            confidence=0.6,
        )
    ]


def extract_obligations(clauses: list[ParsedClause], document_id: UUID) -> list[ParsedObligation]:
    obligations: list[ParsedObligation] = []

    for clause in clauses:
        if not _DIRECTIVE_PATTERN.search(clause.normalized_text):
            continue

        structured = _extract_structured_fields(clause.normalized_text)
        priority_due_days = structured.due_days
        if priority_due_days is None and structured.due_date is not None:
            priority_due_days = _derive_due_days_from_date(structured.due_date)

        confidence, confidence_annotations = _estimate_confidence(
            text=clause.normalized_text,
            owner_hint=structured.owner_hint,
            action_phrase=structured.action_phrase,
            due_days=structured.due_days,
            due_date=structured.due_date,
            temporal_hint=structured.temporal_hint,
        )

        obligation_index = len(obligations) + 1
        obligations.append(
            ParsedObligation(
                id=uuid4(),
                document_id=document_id,
                clause_id=clause.id,
                obligation_code=f"OBL-AUTO-{obligation_index:03d}",
                title=_build_structured_title(structured.action_phrase, clause.normalized_text),
                description=clause.normalized_text,
                owner_hint=structured.owner_hint,
                due_date=structured.due_date,
                status="draft",
                priority=_compute_priority(priority_due_days, clause.normalized_text),
                review_state="pending_review",
                confidence=confidence,
                citation_page_number=clause.page_number,
                citation_clause_span=build_clause_span_token(
                    clause_index=clause.clause_index,
                    page_number=clause.page_number,
                    span_start=clause.span_start,
                    span_end=clause.span_end,
                ),
                metadata={
                    "phase": "phase-b",
                    "source": "structured-obligation-extractor-v1",
                    "extractor_version": "structured-v1",
                    "clause_index": clause.clause_index,
                    "structured_fields": {
                        "owner_hint": structured.owner_hint,
                        "action_phrase": structured.action_phrase,
                        "deadline_source": structured.deadline_source,
                        "temporal_hint": structured.temporal_hint,
                        "due_days": structured.due_days,
                        "due_date": (
                            structured.due_date.isoformat()
                            if structured.due_date is not None
                            else None
                        ),
                    },
                    "confidence_annotations": confidence_annotations,
                },
            )
        )

    return obligations


def build_clause_span_token(
    *,
    clause_index: int,
    page_number: int | None,
    span_start: int | None,
    span_end: int | None,
) -> str:
    if span_start is None or span_end is None:
        return f"clause-{clause_index}"

    if page_number is None:
        return f"c{clause_index}:{span_start}-{span_end}"

    return f"p{page_number}:c{clause_index}:{span_start}-{span_end}"


def _iter_pages(raw_text: str) -> list[tuple[int, str, int]]:
    pages: list[tuple[int, str, int]] = []
    cursor = 0

    for page_number, page_text in enumerate(raw_text.split("\f"), start=1):
        pages.append((page_number, page_text, cursor))
        cursor += len(page_text) + 1

    return pages


def _iter_clause_chunks(page_text: str, page_offset: int) -> list[tuple[str, int, int]]:
    chunks: list[tuple[str, int, int]] = []

    for match in re.finditer(r"[^\n.!?]+(?:[.!?]+)?", page_text):
        chunk = match.group(0)
        if not chunk.strip():
            continue
        span_start = page_offset + match.start()
        span_end = page_offset + match.end()
        chunks.append((chunk, span_start, span_end))

    return chunks


def _normalize_document_text(value: str) -> str:
    sanitized = _sanitize_text(value)
    normalized = sanitized.replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"[ \t]+", " ", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def _normalize_whitespace(value: str) -> str:
    sanitized = _sanitize_text(value)
    return " ".join(sanitized.replace("\r", "\n").split())


def _sanitize_text(value: str) -> str:
    if not value:
        return ""

    cleaned_chars: list[str] = []
    for char in value:
        if char == "\x00":
            continue
        if ord(char) < 32 and char not in {"\n", "\t"}:
            continue
        cleaned_chars.append(char)

    return "".join(cleaned_chars)


def _is_pdf_document(content_type: str, source_file_name: str | None) -> bool:
    if content_type == _PDF_CONTENT_TYPE:
        return True

    if source_file_name is None:
        return False

    return Path(source_file_name).suffix.lower() == ".pdf"


def _decode_pdf_text(payload: bytes, source_file_name: str | None) -> str:
    docling_text = _decode_pdf_with_docling(payload, source_file_name)
    if docling_text:
        return docling_text

    pypdf_text = _decode_pdf_with_pypdf(payload)
    if pypdf_text:
        return pypdf_text

    fallback_text = _extract_binary_printable_text(payload)
    if fallback_text:
        return fallback_text

    raise ValueError(_build_pdf_extraction_error_message())


def _build_pdf_extraction_error_message() -> str:
    have_docling = _load_docling_converter() is not None
    try:
        importlib.import_module("pypdf")
        have_pypdf = True
    except Exception:
        have_pypdf = False

    if have_docling or have_pypdf:
        return (
            "Unable to extract text from PDF: no readable text layer was found. "
            "The file may be a scanned image or use embedded fonts that defeat "
            "text extraction. Try a text-readable PDF, or run OCR (e.g. Tesseract "
            "with the appropriate language pack) before uploading."
        )

    return (
        "Unable to extract text from PDF. Install docling or pypdf for high-quality "
        "parsing or upload a text-readable document."
    )


def _decode_pdf_with_docling(payload: bytes, source_file_name: str | None) -> str | None:
    converter_class = _load_docling_converter()
    if converter_class is None:
        return None

    suffix = Path(source_file_name or "document.pdf").suffix.lower() or ".pdf"
    if suffix != ".pdf":
        suffix = ".pdf"

    temp_file_path: Path | None = None
    with NamedTemporaryFile(delete=False, suffix=suffix) as handle:
        handle.write(payload)
        temp_file_path = Path(handle.name)

    try:
        converter = converter_class()
        result = converter.convert(str(temp_file_path))
    except Exception:
        return None
    finally:
        if temp_file_path is not None:
            temp_file_path.unlink(missing_ok=True)

    text = _coerce_docling_text(result)
    if text is None:
        return None

    normalized = _normalize_document_text(text)
    return normalized or None


def _decode_pdf_with_pypdf(payload: bytes) -> str | None:
    try:
        from io import BytesIO

        from pypdf import PdfReader
    except Exception:
        return None

    try:
        reader = PdfReader(BytesIO(payload))
    except Exception:
        return None

    pages: list[str] = []
    for page in reader.pages:
        try:
            extracted = page.extract_text() or ""
        except Exception:
            continue

        normalized = _normalize_document_text(extracted)
        if not normalized:
            continue

        # When pypdf cannot decode embedded fonts (common for Marathi/Hindi
        # PDFs with custom CID encodings) it sometimes returns text that is
        # mostly Unicode replacement characters or PDF structural bleed.
        # Drop those pages instead of forwarding garbage downstream.
        if _is_pypdf_garbage(normalized):
            continue

        pages.append(normalized)

    if not pages:
        return None

    text = "\f".join(pages)
    return text if _looks_like_natural_language(text) else None


def _is_pypdf_garbage(text: str) -> bool:
    if not text:
        return True

    if _contains_pdf_structure_tokens(text):
        return True

    # � is the Unicode replacement character; pypdf emits it when a
    # glyph has no usable mapping. A handful is fine, a flood means the
    # extraction is unreadable.
    replacement_count = text.count("�")
    if replacement_count and (replacement_count / max(len(text), 1)) > 0.05:
        return True

    return False


def _load_docling_converter() -> type[Any] | None:
    try:
        module = importlib.import_module("docling.document_converter")
    except Exception:
        return None

    converter = getattr(module, "DocumentConverter", None)
    if converter is None:
        return None

    return converter


def _coerce_docling_text(result: object) -> str | None:
    direct_text = getattr(result, "text", None)
    if isinstance(direct_text, str) and direct_text.strip():
        return direct_text

    document = getattr(result, "document", None)
    if document is None:
        return None

    for method_name in ("export_to_markdown", "export_to_text"):
        exporter = getattr(document, method_name, None)
        if not callable(exporter):
            continue

        try:
            value = exporter()
        except Exception:
            continue

        if isinstance(value, str) and value.strip():
            return value

    fallback_text = getattr(document, "text", None)
    if isinstance(fallback_text, str) and fallback_text.strip():
        return fallback_text

    return None


def _extract_binary_printable_text(payload: bytes) -> str | None:
    candidates: list[str] = []

    for raw in re.findall(rb"\(([^()]*)\)", payload):
        segment = _normalize_whitespace(raw.decode("utf-8", errors="ignore"))
        if (
            len(segment) >= 20
            and not _contains_pdf_structure_tokens(segment)
            and _looks_like_natural_language(segment)
        ):
            candidates.append(segment)

    if candidates:
        joined = " ".join(candidates)
        # Defence in depth: re-check the joined output, since segments that
        # individually pass the gate can still combine into something dominated
        # by PDF structure noise.
        if not _contains_pdf_structure_tokens(joined):
            return joined

    utf8_text = _normalize_document_text(payload.decode("utf-8", errors="ignore"))
    if (
        len(utf8_text) >= 20
        and _is_mostly_printable(utf8_text)
        and not _contains_pdf_structure_tokens(utf8_text)
        and _looks_like_natural_language(utf8_text)
    ):
        return utf8_text

    return None


# Tokens that appear in PDF dictionary / object syntax. If any of these show
# up in our "extracted text" it means we are scraping the file's structural
# bytes rather than its content stream — never legitimate document text.
_PDF_STRUCTURE_MARKERS: tuple[str, ...] = (
    "%PDF-",
    " obj",
    "endobj",
    "stream",
    "endstream",
    "xref",
    "/Filter",
    "/Length",
    "/FlateDecode",
    "/Type",
    "/Catalog",
    "/Pages",
    "/Page",
    "/MediaBox",
    "/Font",
    "/Encoding",
    "/Resources",
    "<<",
    ">>",
    "trailer",
    "startxref",
)


def _contains_pdf_structure_tokens(text: str) -> bool:
    if not text:
        return False
    return any(marker in text for marker in _PDF_STRUCTURE_MARKERS)


def _is_mostly_printable(text: str, threshold: float = 0.8) -> bool:
    if not text:
        return False

    printable_count = sum(ch.isprintable() for ch in text)
    ratio = printable_count / len(text)
    return ratio >= threshold


def _looks_like_natural_language(text: str) -> bool:
    if _has_meaningful_indic_content(text):
        return True

    tokens = [token.lower() for token in re.findall(r"[A-Za-z]{2,}", text)]
    if len(tokens) < 4:
        return False

    letter_count = sum(ch.isalpha() for ch in text)
    if letter_count < 20:
        return False

    if (letter_count / len(text)) < 0.45:
        return False

    symbol_count = sum(1 for ch in text if not ch.isalnum() and not ch.isspace())
    if (symbol_count / len(text)) > 0.25:
        return False

    hint_hits = sum(1 for token in tokens if token in _NATURAL_LANGUAGE_HINTS)
    if hint_hits < 2:
        return False

    vowel_count = sum(1 for token in tokens for ch in token if ch in "aeiou")
    if vowel_count == 0:
        return False

    if (vowel_count / letter_count) < 0.20:
        return False

    return True


def _has_meaningful_indic_content(text: str) -> bool:
    if not text:
        return False

    indic_count = sum(1 for ch in text if _is_indic_character(ch))
    if indic_count < 20:
        return False

    symbol_count = sum(1 for ch in text if not ch.isalnum() and not ch.isspace())
    if (symbol_count / len(text)) > 0.4:
        return False

    return True


def _is_indic_character(char: str) -> bool:
    code_point = ord(char)
    for start, end in _INDIC_SCRIPT_RANGES:
        if start <= code_point <= end:
            return True
    return False


def _extract_due_days(text: str) -> int | None:
    match = _DUE_DAYS_PATTERN.search(text)
    if not match:
        return None
    return int(match.group(1))


def _extract_structured_fields(text: str) -> StructuredObligationFields:
    owner_hint = _extract_owner_hint(text)
    action_phrase = _extract_action_phrase(text)
    due_days = _extract_due_days(text)
    due_date: date | None = None
    deadline_source: str | None = None

    if due_days is not None:
        due_date = date.today() + timedelta(days=due_days)
        deadline_source = "relative_days"
    else:
        explicit_due_date = _extract_explicit_due_date(text)
        if explicit_due_date is not None:
            due_date = explicit_due_date
            due_days = _derive_due_days_from_date(explicit_due_date)
            deadline_source = "explicit_date"

    temporal_hint = _extract_temporal_hint(text)
    if deadline_source is None and temporal_hint is not None:
        deadline_source = "temporal_hint"

    return StructuredObligationFields(
        owner_hint=owner_hint,
        action_phrase=action_phrase,
        due_days=due_days,
        due_date=due_date,
        deadline_source=deadline_source,
        temporal_hint=temporal_hint,
    )


def _estimate_confidence(
    *,
    text: str,
    owner_hint: str | None,
    action_phrase: str | None,
    due_days: int | None,
    due_date: date | None,
    temporal_hint: str | None,
) -> tuple[float, dict[str, object]]:
    lowered = text.lower()
    directive_signal = 1.0 if ("shall" in lowered or "must" in lowered) else 0.85
    owner_signal = 1.0 if owner_hint is not None else 0.45

    action_word_count = len(action_phrase.split()) if action_phrase else 0
    if action_word_count >= 3:
        action_signal = 0.95
    elif action_word_count == 2:
        action_signal = 0.8
    elif action_word_count == 1:
        action_signal = 0.65
    else:
        action_signal = 0.4

    if due_days is not None or due_date is not None:
        deadline_signal = 1.0
    elif temporal_hint is not None:
        deadline_signal = 0.7
    else:
        deadline_signal = 0.35

    word_count = len(text.split())
    lexical_clarity_signal = 0.9 if 6 <= word_count <= 40 else 0.7

    components = {
        "directive_signal": round(directive_signal, 2),
        "owner_signal": round(owner_signal, 2),
        "action_signal": round(action_signal, 2),
        "deadline_signal": round(deadline_signal, 2),
        "lexical_clarity_signal": round(lexical_clarity_signal, 2),
    }
    weights = {
        "directive_signal": 0.35,
        "owner_signal": 0.2,
        "action_signal": 0.2,
        "deadline_signal": 0.15,
        "lexical_clarity_signal": 0.1,
    }

    final_score = sum(components[key] * weights[key] for key in weights)
    final_score = min(max(final_score, 0.4), 0.95)

    rationale: list[str] = []
    if owner_hint is None:
        rationale.append("Owner was not clearly identified from the clause prefix.")
    if action_phrase is None:
        rationale.append("Action phrase was not confidently extracted after directive keyword.")
    if due_days is None and due_date is None and temporal_hint is None:
        rationale.append("No explicit deadline signal was detected.")

    annotations = {
        "extractor_version": "structured-v1",
        "components": components,
        "weights": weights,
        "rationale": rationale,
        "signals": {
            "owner_detected": owner_hint is not None,
            "action_detected": action_phrase is not None,
            "relative_due_days": due_days,
            "explicit_due_date": due_date.isoformat() if due_date is not None else None,
            "temporal_hint": temporal_hint,
        },
    }

    return round(final_score, 2), annotations


def _extract_action_phrase(text: str) -> str | None:
    directive_match = _DIRECTIVE_SPLIT_PATTERN.search(text)
    if directive_match is None:
        return None

    action_phrase = text[directive_match.end() :].strip(" .;:-")
    if not action_phrase:
        return None

    return re.sub(r"\s+", " ", action_phrase)[:220]


def _extract_explicit_due_date(text: str) -> date | None:
    match = _EXPLICIT_DATE_PATTERN.search(text)
    if match is None:
        return None

    value = match.group("value").strip().replace(",", "")
    for fmt in (
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%d/%m/%y",
        "%d-%m-%y",
        "%d %B %Y",
        "%d %b %Y",
    ):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue

    return None


def _extract_temporal_hint(text: str) -> str | None:
    match = _TEMPORAL_HINT_PATTERN.search(text)
    if match is None:
        return None

    return match.group(0).strip()


def _derive_due_days_from_date(due_date: date | None) -> int | None:
    if due_date is None:
        return None

    return max((due_date - date.today()).days, 0)


def _build_structured_title(action_phrase: str | None, text: str) -> str:
    if action_phrase is None:
        return _build_title(text)

    return _build_title(action_phrase)


def _build_title(text: str) -> str:
    compact = text.strip().rstrip(".")
    if len(compact) <= 96:
        return compact
    return f"{compact[:93]}..."


def _extract_owner_hint(text: str) -> str | None:
    match = re.search(
        r"^(?P<owner>.+?)\s+(?:shall|must|is directed to|are directed to)\b",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return None

    owner = match.group("owner").strip(" ,;:-")
    if not owner:
        return None
    return owner[:120]


def _compute_priority(due_days: int | None, text: str) -> str:
    lowered = text.lower()
    if "immediate" in lowered or "forthwith" in lowered:
        return "critical"
    if due_days is not None and due_days <= 3:
        return "critical"
    if due_days is not None and due_days <= 7:
        return "high"
    if due_days is not None and due_days <= 21:
        return "medium"
    return "low"
