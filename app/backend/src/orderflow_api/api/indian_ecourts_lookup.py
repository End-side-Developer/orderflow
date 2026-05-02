from __future__ import annotations

import base64
import hashlib
import json
import re
from functools import lru_cache
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from pypdf import PdfReader

from orderflow_api.schemas.documents import (
    IndianECourtsCCMSEnvelope,
    IndianECourtsCISEnvelope,
    IndianECourtsIntakeRequest,
    IndianECourtsLookupRecord,
)

DHC_HOST = "delhihighcourt.nic.in"
DHC_JUDGMENT_PATH_PREFIX = "/app/showFileJudgment/"
DHC_LATEST_JUDGMENTS_URL = "https://delhihighcourt.nic.in/web/hi/judgement/fetch-data"
ECOURTS_SERVICE_HOSTS = {"services.ecourts.gov.in", "www.services.ecourts.gov.in"}
MAX_LOOKUP_PDF_SIZE_BYTES = 20 * 1024 * 1024


def lookup_indian_ecourts_prefill(identifier: str) -> IndianECourtsLookupRecord:
    normalized_identifier = identifier.strip()
    if not normalized_identifier:
        raise ValueError("Identifier is required")

    source_url = _resolve_source_url(normalized_identifier)
    is_dhc_source = _is_dhc_source_url(source_url)
    payload = _download_pdf(source_url)
    source_file_name = _extract_file_name(source_url)
    source_file_type = "application/pdf"

    pdf_text = _extract_pdf_text(payload)
    cis_case_id = _extract_case_id_from_text(pdf_text) or _derive_case_id_from_token(source_url)
    if not cis_case_id and "/" in normalized_identifier:
        cis_case_id = normalized_identifier

    order_date = _extract_order_date_from_text(pdf_text) or _extract_order_date_from_token(source_url)
    judge_names = _extract_judge_names(pdf_text)
    petitioners, respondents = _extract_parties(pdf_text)
    case_type = _derive_case_type_from_case_id(cis_case_id)

    token = _extract_token_from_url(source_url)
    ccms_reference_id = f"DHC-CCMS-AUTO-{token[:72]}"
    receipt_suffix = token[-16:] if len(token) > 16 else token

    cis_envelope = IndianECourtsCISEnvelope(
        case_id=cis_case_id,
        court_name="High Court of Delhi" if is_dhc_source else "Indian eCourts",
        court_code="DHC" if is_dhc_source else None,
        order_date=order_date,
        bench=", ".join(judge_names[:2]) if judge_names else None,
        petitioners=petitioners or None,
        respondents=respondents or None,
        parties=(petitioners + respondents) if (petitioners or respondents) else None,
        case_type=case_type,
        filing_number=cis_case_id,
        judge_names=judge_names or None,
        hearing_stage="Judgment pronounced" if is_dhc_source else None,
        state="Delhi" if is_dhc_source else None,
        district="New Delhi" if is_dhc_source else None,
        department_tags=_derive_department_tags(cis_case_id),
    )

    envelope = IndianECourtsIntakeRequest(
        ccms=IndianECourtsCCMSEnvelope(
            reference_id=ccms_reference_id,
            delivery_timestamp=datetime.now(UTC),
            document_type="judgment",
            source_url=source_url,
            source_gateway="indian-ecourts-service",
            receipt_id=f"DHC-EC-AUTO-{receipt_suffix}",
        ),
        cis=cis_envelope,
        source_file_name=source_file_name,
        source_file_type=source_file_type,
        additional_metadata={
            "lookup_identifier": normalized_identifier,
            "lookup_mode": (
                "delhi_high_court_public_judgment_lookup"
                if is_dhc_source
                else "indian_ecourts_direct_pdf_url"
            ),
            "source_url": source_url,
        },
    )

    return IndianECourtsLookupRecord(
        identifier=normalized_identifier,
        resolved_source_url=source_url,
        source_file_name=source_file_name,
        source_file_type=source_file_type,
        file_content_base64=base64.b64encode(payload).decode("ascii"),
        envelope=envelope,
        note=(
            "Prefilled using Delhi High Court public judgment pages. "
            "Case-search forms on the eCourts portal are captcha-protected, so this flow uses "
            "public judgment links and PDF text heuristics."
            if is_dhc_source
            else (
                "Prefilled using a direct Indian eCourts PDF URL. "
                "Case-search forms on services.ecourts.gov.in are captcha-protected, "
                "so provide a direct order/judgment PDF URL when using this mode."
            )
        ),
    )


def _resolve_source_url(identifier: str) -> str:
    if identifier.lower().startswith(("http://", "https://")):
        return _normalize_supported_judgment_url(identifier)

    token_match = re.fullmatch(r"[A-Za-z0-9_]+(?:\.pdf)?", identifier)
    if token_match:
        token = identifier[:-4] if identifier.lower().endswith(".pdf") else identifier
        return f"https://{DHC_HOST}{DHC_JUDGMENT_PATH_PREFIX}{token}.pdf"

    sample_url = _resolve_case_id_from_local_samples(identifier)
    if sample_url is not None:
        return sample_url

    case_pattern = _to_case_pattern(identifier)
    if case_pattern:
        # The case-id path scrapes the DHC "latest judgments" page. If the
        # case isn't in that small window, we cannot resolve it via a case
        # id alone — eCourts case-search forms are captcha-protected.
        scrape_failed = False
        try:
            links = _fetch_latest_judgment_links()
        except Exception:
            links = []
            scrape_failed = True
        for link in links:
            if case_pattern in link.upper():
                return _normalize_dhc_judgment_url(link)

        sample_ids = sorted(_load_local_case_sample_map().keys())
        sample_hint = (
            ", ".join(sample_ids[:3]) if sample_ids else "no local samples loaded"
        )
        scrape_note = (
            "DHC latest-judgments fetch failed."
            if scrape_failed
            else f"Searched {len(links)} entries on the DHC latest-judgments page."
        )
        raise ValueError(
            f"Case id '{identifier}' was understood but no matching judgment "
            f"was found. {scrape_note} The case-id path only resolves cases "
            f"currently listed on https://delhihighcourt.nic.in/web/hi/judgement/fetch-data "
            f"or one of the bundled samples ({sample_hint}). "
            f"To ingest any other case, paste the full DHC judgment URL or its "
            f"showFileJudgment token instead."
        )

    raise ValueError(
        "Could not understand the identifier. Provide one of: "
        "(a) a delhihighcourt.nic.in /app/showFileJudgment/<token>.pdf URL, "
        "(b) the bare token, "
        "(c) a direct services.ecourts.gov.in PDF URL, "
        "or (d) a case id like 'W.P.(C) 8524/2025' (only resolves if it is "
        "currently on the DHC latest-judgments page or bundled as a sample)."
    )


def _normalize_supported_judgment_url(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()

    if host in {DHC_HOST, f"www.{DHC_HOST}"}:
        return _normalize_dhc_judgment_url(url)

    if host in ECOURTS_SERVICE_HOSTS:
        return _normalize_ecourts_pdf_url(url)

    raise ValueError(
        "Only delhihighcourt.nic.in showFileJudgment links or direct services.ecourts.gov.in "
        "PDF links are supported"
    )


def _normalize_ecourts_pdf_url(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host not in ECOURTS_SERVICE_HOSTS:
        raise ValueError("Only services.ecourts.gov.in links are supported in this mode")

    if not parsed.path.lower().endswith(".pdf"):
        raise ValueError(
            "services.ecourts.gov.in case-search pages are captcha-protected; provide a direct PDF URL"
        )

    normalized = f"https://{host}{parsed.path}"
    if parsed.query:
        normalized = f"{normalized}?{parsed.query}"
    return normalized


def _is_dhc_source_url(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    return host in {DHC_HOST, f"www.{DHC_HOST}"}


def _normalize_dhc_judgment_url(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host not in {DHC_HOST, f"www.{DHC_HOST}"}:
        raise ValueError("Only delhihighcourt.nic.in judgment links are supported")

    marker = "/showFileJudgment/"
    if marker not in parsed.path:
        raise ValueError("URL must point to /app/showFileJudgment/<token>.pdf")

    token = parsed.path.split(marker, maxsplit=1)[1].strip("/")
    if token.lower().endswith(".pdf"):
        token = token[:-4]
    if not re.fullmatch(r"[A-Za-z0-9_]+", token):
        raise ValueError("Judgment token is invalid")

    return f"https://{DHC_HOST}{DHC_JUDGMENT_PATH_PREFIX}{token}.pdf"


def _fetch_latest_judgment_links() -> list[str]:
    request = Request(
        DHC_LATEST_JUDGMENTS_URL,
        headers={"User-Agent": "OrderFlow/1.0 (+theme-11-orderflow)"},
    )
    with urlopen(request, timeout=20) as response:
        html = response.read().decode("utf-8", errors="ignore")

    matches = re.findall(
        r"(?:https?://delhihighcourt\.nic\.in)?/app/showFileJudgment/[A-Za-z0-9_]+\.pdf",
        html,
        flags=re.IGNORECASE,
    )

    unique_links: list[str] = []
    seen: set[str] = set()
    for match in matches:
        link = (
            match
            if match.lower().startswith("http")
            else f"https://{DHC_HOST}{match if match.startswith('/') else '/' + match}"
        )
        normalized = _normalize_dhc_judgment_url(link)
        if normalized not in seen:
            seen.add(normalized)
            unique_links.append(normalized)

    return unique_links


def _download_pdf(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "OrderFlow/1.0 (+theme-11-orderflow)"})
    with urlopen(request, timeout=30) as response:
        payload = response.read()

    if len(payload) > MAX_LOOKUP_PDF_SIZE_BYTES:
        raise ValueError("The judgment PDF is too large for auto-prefill")
    if not payload.startswith(b"%PDF"):
        raise ValueError("Resolved source is not a valid PDF")

    return payload


def _extract_file_name(url: str) -> str:
    parsed = urlparse(url)
    file_name = Path(parsed.path).name.strip()
    if file_name.lower().endswith(".pdf"):
        return file_name

    token = _extract_token_from_url(url)
    return f"{token}.pdf"


def _extract_token_from_url(url: str) -> str:
    marker = "/showFileJudgment/"
    parsed = urlparse(url)

    if marker in parsed.path:
        token = parsed.path.split(marker, maxsplit=1)[1].strip("/")
        if token.lower().endswith(".pdf"):
            token = token[:-4]
        return token

    path_name = Path(parsed.path).name.strip()
    if path_name.lower().endswith(".pdf"):
        path_name = path_name[:-4]

    token_base = path_name or f"url_{hashlib.sha1(url.encode('utf-8')).hexdigest()[:16]}"
    normalized = re.sub(r"[^A-Za-z0-9_]+", "_", token_base).strip("_")
    if not normalized:
        normalized = f"url_{hashlib.sha1(url.encode('utf-8')).hexdigest()[:16]}"

    return normalized[:120]


def _to_case_pattern(case_id: str) -> str | None:
    match = re.search(
        r"(?P<type>[A-Za-z().\s-]+?)\s*(?P<number>\d+)\s*/\s*(?P<year>(?:19|20)\d{2})",
        case_id,
    )
    if not match:
        return None

    case_code = _map_case_type_to_code(match.group("type"))
    case_number = str(int(match.group("number")))
    case_year = match.group("year")
    return f"{case_code}{case_number}{case_year}".upper()


def _map_case_type_to_code(raw_case_type: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]", "", raw_case_type).upper()
    explicit_map = {
        "WPC": "CW",
        "WPCRL": "CRLW",
        "CRLA": "CRLA",
        "CRLMA": "CRLMA",
        "BAILAPPLN": "BA",
        "BA": "BA",
        "LPA": "LPA",
        "FAO": "FAO",
        "AA": "AA",
        "OMPCOMM": "OMPCOMM",
        "OMPICOMM": "OMPICOMM",
        "OMPENFCOMM": "OMPENFCOMM",
    }
    if normalized in explicit_map:
        return explicit_map[normalized]

    for prefix, value in explicit_map.items():
        if normalized.startswith(prefix):
            return value

    return normalized


def _extract_pdf_text(payload: bytes) -> str:
    try:
        reader = PdfReader(BytesIO(payload))
    except Exception:
        return ""

    snippets: list[str] = []
    for page in reader.pages[:2]:
        try:
            page_text = page.extract_text() or ""
        except Exception:
            page_text = ""
        if page_text:
            snippets.append(page_text)

    return "\n".join(snippets)


def _extract_case_id_from_text(text: str) -> str | None:
    if not text:
        return None

    match = re.search(
        r"([A-Z][A-Z()./\-\s]{1,40}\d+\s*/\s*(?:19|20)\d{2})",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return None

    return " ".join(match.group(1).split())


def _derive_case_id_from_token(url: str) -> str | None:
    token = _extract_token_from_url(url).upper().split("_", maxsplit=1)[0]
    match = re.search(r"([A-Z]{2,})(\d{1,8})((?:19|20)\d{2})$", token)
    if not match:
        return None

    case_code, case_number, case_year = match.groups()
    display_case_type = _display_case_type(case_code)
    return f"{display_case_type} {int(case_number)}/{case_year}"


def _display_case_type(case_code: str) -> str:
    reverse_map = {
        "CW": "W.P.(C)",
        "CRLW": "CRL.W",
        "CRLA": "CRL.A.",
        "CRLMA": "CRL.M.A.",
        "BA": "BAIL APPLN.",
        "LPA": "LPA",
        "FAO": "FAO",
        "AA": "AA",
        "OMPCOMM": "O.M.P.(COMM)",
        "OMPICOMM": "O.M.P.(I)(COMM)",
        "OMPENFCOMM": "O.M.P.(ENF)(COMM)",
    }
    return reverse_map.get(case_code, case_code)


def _extract_order_date_from_token(url: str) -> str | None:
    token = _extract_token_from_url(url)
    match = re.search(r"(\d{2})(\d{2})((?:19|20)\d{2})", token)
    if not match:
        return None

    day, month, year = match.groups()
    return _safe_iso_date(day=day, month=month, year=year)


def _extract_order_date_from_text(text: str) -> str | None:
    if not text:
        return None

    patterns = [
        r"Date\s+of\s+(?:Order|Judgment)\s*[:\-]?\s*(\d{1,2}[./-]\d{1,2}[./-](?:19|20)\d{2})",
        r"Pronounced\s+on\s*[:\-]?\s*(\d{1,2}[./-]\d{1,2}[./-](?:19|20)\d{2})",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue

        raw = match.group(1).replace(".", "-").replace("/", "-")
        parts = raw.split("-")
        if len(parts) != 3:
            continue
        day, month, year = parts
        iso_date = _safe_iso_date(day=day.zfill(2), month=month.zfill(2), year=year)
        if iso_date is not None:
            return iso_date

    return None


def _safe_iso_date(*, day: str, month: str, year: str) -> str | None:
    try:
        parsed = datetime.strptime(f"{day}-{month}-{year}", "%d-%m-%Y")
    except ValueError:
        return None
    return parsed.strftime("%Y-%m-%d")


def _extract_judge_names(text: str) -> list[str]:
    if not text:
        return []

    section = text
    coram_index = text.upper().find("CORAM")
    if coram_index >= 0:
        section = text[coram_index : coram_index + 1200]

    candidates = re.findall(
        r"HON'?BLE\s+[^\n]{0,24}JUSTICE\s+[A-Z][A-Z\s.]{2,80}",
        section,
        flags=re.IGNORECASE,
    )

    cleaned: list[str] = []
    for candidate in candidates:
        normalized = " ".join(candidate.replace("\t", " ").split())
        normalized = normalized.rstrip(".:;,")
        if normalized and normalized not in cleaned:
            cleaned.append(normalized)

    return cleaned[:4]


def _extract_parties(text: str) -> tuple[list[str], list[str]]:
    if not text:
        return [], []

    petitioner_pattern = re.compile(
        r"^\s*([A-Z0-9 .,()&'/-]{3,120})\s*\.{2,}\s*(?:Petitioner|Appellant|Applicant)s?\b",
        flags=re.IGNORECASE | re.MULTILINE,
    )
    respondent_pattern = re.compile(
        r"^\s*([A-Z0-9 .,()&'/-]{3,120})\s*\.{2,}\s*(?:Respondent|Defendant)s?\b",
        flags=re.IGNORECASE | re.MULTILINE,
    )

    petitioners = _unique_clean_party_names([match.group(1) for match in petitioner_pattern.finditer(text)])
    respondents = _unique_clean_party_names([match.group(1) for match in respondent_pattern.finditer(text)])

    if petitioners or respondents:
        return petitioners, respondents

    versus_match = re.search(
        r"([A-Z0-9 .,()&'/-]{3,120})\s+VERSUS\s+([A-Z0-9 .,()&'/-]{3,120})",
        text,
        flags=re.IGNORECASE,
    )
    if versus_match:
        return (
            _unique_clean_party_names([versus_match.group(1)]),
            _unique_clean_party_names([versus_match.group(2)]),
        )

    return [], []


def _unique_clean_party_names(values: list[str]) -> list[str]:
    cleaned: list[str] = []
    for value in values:
        normalized = " ".join(value.strip().split())
        normalized = normalized.rstrip(".:;,")
        if len(normalized) < 3:
            continue
        if normalized not in cleaned:
            cleaned.append(normalized)
    return cleaned[:6]


def _derive_case_type_from_case_id(case_id: str | None) -> str | None:
    if not case_id:
        return None

    match = re.match(r"\s*([A-Za-z().\s-]+?)\s+\d+\s*/\s*(?:19|20)\d{2}", case_id)
    if not match:
        return None

    return " ".join(match.group(1).split())


def _derive_department_tags(case_id: str | None) -> list[str] | None:
    if not case_id:
        return None

    upper = case_id.upper()
    if "CRL" in upper or "BAIL" in upper:
        return ["Criminal Law", "High Court Litigation"]
    if "W.P" in upper or upper.startswith("CW"):
        return ["Administrative Law", "Constitutional Law"]
    if "OMP" in upper or "ARB" in upper or upper.startswith("AA"):
        return ["Commercial Law", "Arbitration"]

    return ["High Court Litigation"]


def _resolve_case_id_from_local_samples(case_id: str) -> str | None:
    normalized_case_id = _normalize_case_id_for_match(case_id)
    if not normalized_case_id:
        return None

    sample_map = _load_local_case_sample_map()
    return sample_map.get(normalized_case_id)


@lru_cache(maxsize=1)
def _load_local_case_sample_map() -> dict[str, str]:
    root_dir = Path(__file__).resolve().parents[5]
    sample_dir = root_dir / "docs" / "samples" / "court-cases"
    if not sample_dir.exists():
        return {}

    sample_map: dict[str, str] = {}
    for sample_path in sample_dir.glob("*.json"):
        try:
            payload = json.loads(sample_path.read_text(encoding="utf-8"))
        except Exception:
            continue

        cis_case_id = (
            payload.get("cis", {}).get("case_id")
            if isinstance(payload.get("cis"), dict)
            else None
        )
        ccms_source_url = (
            payload.get("ccms", {}).get("source_url")
            if isinstance(payload.get("ccms"), dict)
            else None
        )
        metadata_source_url = (
            payload.get("additional_metadata", {}).get("source_url")
            if isinstance(payload.get("additional_metadata"), dict)
            else None
        )

        if not isinstance(cis_case_id, str):
            continue

        source_url = ccms_source_url if isinstance(ccms_source_url, str) else metadata_source_url
        if not isinstance(source_url, str):
            continue

        try:
            normalized_url = _normalize_dhc_judgment_url(source_url)
        except Exception:
            continue

        sample_map[_normalize_case_id_for_match(cis_case_id)] = normalized_url

    return sample_map


def _normalize_case_id_for_match(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", value).upper()
