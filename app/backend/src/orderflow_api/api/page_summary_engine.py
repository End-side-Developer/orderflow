"""
Page-by-page summary extraction engine.

Generates AI-powered summaries of court judgment pages, preserving
legal context and identifying critical decision points.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, AsyncGenerator
from uuid import UUID

from orderflow_api.api.geocoding_service import build_extracted_places, geocode_places
from orderflow_api.api.page_summary_persistence import (
    MAX_PAGE_SUMMARY_SOURCE_EXCERPT_CHARS,
    create_page_summary,
    get_cached_page_summary,
)
from orderflow_api.core.config import settings
from orderflow_api.core.gemini_client import call_gemini_json, extract_gemini_text
from orderflow_api.core.hash_utils import calculate_page_content_hash
from orderflow_api.core.ai_versions import PAGE_EXTRACTION_PROMPT_VERSION
from orderflow_api.schemas.page_summaries import (
    ExtractedPlace,
    PageSummaryRecord,
)

logger = logging.getLogger(__name__)

_SPECIALIZATION_KEYWORDS: dict[str, tuple[str, ...]] = {
    "criminal": (
        "criminal",
        "fir",
        "bail",
        "ipc",
        "crpc",
        "arrest",
        "custody",
        "charge sheet",
        "investigation officer",
    ),
    "civil": (
        "civil",
        "injunction",
        "specific performance",
        "decree",
        "plaintiff",
        "defendant",
        "partition",
        "civil suit",
    ),
    "family": (
        "family",
        "maintenance",
        "matrimonial",
        "custody of child",
        "domestic violence",
        "divorce",
        "family court",
    ),
    "corporate": (
        "corporate",
        "contract",
        "agreement",
        "shareholder",
        "insolvency",
        "board resolution",
        "company",
        "corporate debtor",
    ),
    "tax": (
        "tax",
        "gst",
        "income tax",
        "assessment year",
        "penalty",
        "tax demand",
        "it act",
    ),
    "labour": (
        "labour",
        "labor",
        "industrial dispute",
        "workman",
        "wages",
        "labour court",
        "termination",
        "gratuity",
    ),
    "ipr": (
        "ipr",
        "trademark",
        "patent",
        "copyright",
        "intellectual property",
        "infringement",
        "design registration",
    ),
    "consumer": (
        "consumer",
        "consumer forum",
        "deficiency in service",
        "compensation",
        "consumer complaint",
        "refund",
    ),
    "constitutional": (
        "constitutional",
        "article 14",
        "article 19",
        "article 21",
        "article 226",
        "article 32",
        "fundamental rights",
        "writ petition",
    ),
}

_CATEGORY_HINTS: dict[str, tuple[str, ...]] = {
    "order/direction": ("civil", "constitutional"),
    "legal analysis": ("constitutional", "civil"),
    "argument": ("civil",),
    "evidence": ("criminal",),
}

_KNOWN_INDIAN_PLACE_NAMES = (
    "Delhi",
    "New Delhi",
    "Mumbai",
    "Bengaluru",
    "Bangalore",
    "Chennai",
    "Kolkata",
    "Hyderabad",
    "Pune",
    "Ahmedabad",
    "Jaipur",
    "Lucknow",
    "Patna",
    "Bhopal",
    "Indore",
    "Gurugram",
    "Gurgaon",
    "Noida",
    "Chandigarh",
    "Kochi",
    "Thiruvananthapuram",
    "Guwahati",
    "Cuttack",
)

_KNOWN_INDIAN_STATES = (
    "Andhra Pradesh",
    "Arunachal Pradesh",
    "Assam",
    "Bihar",
    "Chhattisgarh",
    "Goa",
    "Gujarat",
    "Haryana",
    "Himachal Pradesh",
    "Jharkhand",
    "Karnataka",
    "Kerala",
    "Madhya Pradesh",
    "Maharashtra",
    "Manipur",
    "Meghalaya",
    "Mizoram",
    "Nagaland",
    "Odisha",
    "Punjab",
    "Rajasthan",
    "Sikkim",
    "Tamil Nadu",
    "Telangana",
    "Tripura",
    "Uttar Pradesh",
    "Uttarakhand",
    "West Bengal",
    "Delhi",
    "Jammu and Kashmir",
    "Ladakh",
    "Puducherry",
)


def infer_advocate_specialization_from_signals(
    *,
    page_category: str | None = None,
    text: str | None = None,
) -> str | None:
    """Infer a directory specialization label from page-level legal signals."""
    haystack = (text or "").lower()
    scores = {name: 0 for name in _SPECIALIZATION_KEYWORDS}

    for specialization, keywords in _SPECIALIZATION_KEYWORDS.items():
        for keyword in keywords:
            if keyword in haystack:
                scores[specialization] += 1

    category = (page_category or "").strip().lower()
    for specialization in _CATEGORY_HINTS.get(category, ()):
        if specialization in scores:
            scores[specialization] += 1

    top_specialization, top_score = max(scores.items(), key=lambda item: item[1])
    if top_score <= 0:
        return None
    return top_specialization


def _snippet(text: str, start: int, end: int, *, radius: int = 60) -> str:
    left = max(0, start - radius)
    right = min(len(text), end + radius)
    return re.sub(r"\s+", " ", text[left:right]).strip()


def _dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _safe_error_text(error: Exception) -> str:
    text = str(error)
    text = re.sub(r"api[_-]?key=[^\s,;]+", "[redacted credential]", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(?:sk|AIza)[A-Za-z0-9_\-]{8,}\b", "[redacted]", text)
    return text


class PageSummaryExtractor:
    """
    Extract AI-powered summaries for each page of a judgment.

    Responsibilities:
    1. Generate concise summaries (2-3 sentences) preserving legal context
    2. Extract key points (3-5 bullets per page)
    3. Identify important highlights with significance levels
    4. Find cross-page context links (explicit and thematic)
    5. Link obligations to their source pages
    """

    def __init__(
        self,
        ai_provider: str,
        model: str,
        api_key: str | None = None,
        temperature: float = 0.3,
    ):
        """
        Initialize the extractor.

        Args:
            ai_provider: "openai" or "anthropic"
            model: Model name (e.g., "gpt-4o" or "claude-3-opus")
            api_key: Optional API key (can load from env if not provided)
            temperature: Low temperature for deterministic legal analysis
        """
        self.ai_provider = ai_provider
        self.model = model
        self.api_key = api_key
        self.temperature = temperature

    async def extract_page_summaries(
        self,
        document_id: UUID,
        pages: dict[int, str],
        obligations: dict[int, list[UUID]] | None = None,
        bypass_cache: bool = False,
    ) -> AsyncGenerator[PageSummaryRecord, None]:
        """
        Extract summaries for all pages.

        Args:
            document_id: Document UUID
            pages: {page_number: page_text}
            obligations: {page_number: [obligation_ids]} (optional)

        Yields:
            PageSummaryRecord objects ordered by page number
        """
        if obligations is None:
            obligations = {}

        total_pages = len(pages)

        for page_num in sorted(pages.keys()):
            page_text = pages[page_num]
            content_hash = calculate_page_content_hash(page_text)

            try:
                # Check cache before AI call
                cached_summary = None
                if not bypass_cache:
                    cached_summary = get_cached_page_summary(
                        document_id=document_id,
                        page_number=page_num,
                        content_hash=content_hash,
                        prompt_version=PAGE_EXTRACTION_PROMPT_VERSION,
                        ai_model=self.model,
                        ai_provider=self.ai_provider,
                    )

                # Get obligations on this page
                page_obligations = obligations.get(page_num, [])

                if cached_summary is not None:
                    # Update obligations if caller passed new ones
                    cached_summary.obligation_ids = page_obligations
                    yield cached_summary
                    logger.info(
                        f"Cache hit for page {page_num}/{total_pages}",
                        extra={"document_id": str(document_id)},
                    )
                    continue

                # AI call for this page
                extraction = await self._ai_extract_page(
                    page_num=page_num,
                    page_text=page_text,
                    total_pages=total_pages,
                )

                # Find context links to other pages
                context_links = self._find_context_links(
                    page_num=page_num,
                    page_text=page_text,
                    all_pages=pages,
                )

                # Get obligations on this page
                page_obligations = obligations.get(page_num, [])
                raw_places = extraction.get("places", [])
                place_candidates = (
                    [item for item in raw_places if isinstance(item, dict)]
                    if isinstance(raw_places, list)
                    else []
                )
                extracted_places = geocode_places(
                    build_extracted_places(place_candidates, page_number=page_num)
                )

                # Create and persist summary record
                summary_record = create_page_summary(
                    document_id=document_id,
                    page_number=page_num,
                    page_text=page_text,
                    summary=extraction.get("summary", ""),
                    key_points=extraction.get("key_points", []),
                    important_highlights=extraction.get("highlights", []),
                    entities=_dict_list(extraction.get("entities")),
                    dates=_dict_list(extraction.get("dates")),
                    directions=_dict_list(extraction.get("directions")),
                    departments=_dict_list(extraction.get("departments")),
                    context_links=[link for link in context_links],
                    obligation_ids=page_obligations,
                    extracted_places=extracted_places,
                    confidence=extraction.get("confidence", 0.85),
                    extraction_mode="ai",
                    ai_model=self.model,
                    ai_provider=self.ai_provider,
                    content_hash=content_hash,
                    prompt_version=PAGE_EXTRACTION_PROMPT_VERSION,
                    source_excerpt=page_text[:MAX_PAGE_SUMMARY_SOURCE_EXCERPT_CHARS],
                )

                yield summary_record
                logger.info(
                    f"Extracted summary for page {page_num}/{total_pages}",
                    extra={"document_id": str(document_id)},
                )

            except Exception as exc:
                logger.error(
                    "Failed to extract summary for page %s: %s",
                    page_num,
                    type(exc).__name__,
                    extra={"document_id": str(document_id)},
                )
                # Continue with next page on error
                continue

    async def extract_places_for_page(
        self,
        *,
        page_num: int,
        page_text: str,
        state_hint: str | None = None,
        district_hint: str | None = None,
        court_fallback_query: str | None = None,
    ) -> list[ExtractedPlace]:
        """Refresh only map-ready place extraction for an existing page."""
        candidates: list[dict[str, Any]] = []

        try:
            extraction = await self._ai_extract_places_only(
                page_num=page_num,
                page_text=page_text,
                state_hint=state_hint,
                district_hint=district_hint,
            )
            raw_places = extraction.get("places", [])
            if isinstance(raw_places, list):
                candidates = [item for item in raw_places if isinstance(item, dict)]
        except Exception as exc:
            logger.warning(
                "AI place extraction failed for page %s (provider=%s): %s: %s",
                page_num,
                self.ai_provider,
                type(exc).__name__,
                exc,
            )

        if not candidates:
            candidates = self._deterministic_place_candidates(
                page_text,
                state_hint=state_hint,
                district_hint=district_hint,
            )

        places = build_extracted_places(candidates, page_number=page_num)
        return geocode_places(
            places,
            state_hint=state_hint,
            court_fallback_query=court_fallback_query,
        )

    async def _ai_extract_page(
        self,
        page_num: int,
        page_text: str,
        total_pages: int,
    ) -> dict[str, Any]:
        """
        Call LLM to extract summary, key points, and highlights.

        Returns:
            {
                "summary": str,
                "key_points": [str],
                "highlights": [{"text": str, "significance": str, "relevance": str}],
                "confidence": float
            }
        """
        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(page_num, page_text, total_pages)

        try:
            if self.ai_provider == "openai":
                return await self._call_openai(system_prompt, user_prompt)
            elif self.ai_provider == "anthropic":
                return await self._call_anthropic(system_prompt, user_prompt)
            elif self.ai_provider == "gemini":
                return await self._call_gemini(system_prompt, user_prompt)
            else:
                raise ValueError(f"Unsupported AI provider: {self.ai_provider}")
        except Exception as exc:
            logger.error(
                "AI extraction failed for page %s (provider=%s, model=%s): %s: %s",
                page_num,
                self.ai_provider,
                self.model,
                type(exc).__name__,
                _safe_error_text(exc),
            )
            # Fallback to deterministic extraction
            result = self._deterministic_extract_page(page_text)
            result["ai_fallback"] = True
            result["ai_fallback_reason"] = f"{type(exc).__name__}: {_safe_error_text(exc)}"
            return result

    def _build_system_prompt(self) -> str:
        """System prompt for AI page analysis."""
        return """You are a legal document analyst specializing in court judgments.
Your task is to analyze pages of judgment documents and extract:

1. SUMMARY: Capture the page's essence in 2-3 sentences without losing legal context
   - Include what happened on this page
   - What was decided or ruled
   - Any critical facts or evidence presented

2. KEY_POINTS: Extract 3-5 important statements or findings from this page
   - Each point should be actionable or relevant to execution
   - Points should be specific, not generic

3. HIGHLIGHTS: Identify critical quotes or phrases that affect judgment or obligations
   - Each highlight should be a direct quote or key phrase
   - Include significance level (critical/important/contextual)
   - Explain why it matters for decision-making

4. ENTITIES: Extract important names and institutions on this page
   - Include parties, departments, officers, courts, judges, institutions, and advocates when useful
   - Explain their role if visible from the page

5. DATES: Extract dates and timelines on this page
   - Mark inferred timelines as is_inferred=true
   - Do not invent dates that are not stated or safely inferable

6. DIRECTIONS: Extract legal or administrative directions on this page
   - Mark whether each appears mandatory, advisory, or needs_review
   - Mark whether compliance is required: yes, no, or needs_review

7. DEPARTMENTS: Extract government departments or responsible authorities
   - Include source location and role when visible

8. PLACES: Identify Indian places that physically exist and could be plotted on a map
   - Include courts, cities, districts, property addresses, incident sites, and jurisdictions
   - Skip abstract references such as "petitioner's residence" without a town or address
   - Prefer the most specific form available
   - Same place mentioned multiple times: return once with mention_count

Return valid JSON with this exact structure:
{
    "summary": "string (2-3 sentences, preserving legal context)",
    "key_points": ["point1", "point2", "point3"],
    "highlights": [
        {
            "text": "exact quote or key phrase",
            "significance": "critical|important|contextual",
            "relevance": "one sentence explaining why this matters"
        }
    ],
    "entities": [
        {
            "name": "entity name",
            "entity_type": "petitioner|respondent|department|officer|court|judge|advocate|institution|other",
            "role": "role on this page or null",
            "source_location": "paragraph/line/source clue or null",
            "confidence": 0.85
        }
    ],
    "dates": [
        {
            "date_text": "date or timeline text",
            "label": "order date|deadline|hearing date|limitation period|other",
            "source_location": "paragraph/line/source clue or null",
            "is_inferred": false,
            "confidence": 0.85
        }
    ],
    "directions": [
        {
            "direction_text": "direction in simple English",
            "source_location": "paragraph/line/source clue or null",
            "directive_kind": "mandatory|advisory|needs_review",
            "compliance_required": "yes|no|needs_review",
            "confidence": 0.85
        }
    ],
    "departments": [
        {
            "name": "department or authority",
            "role": "responsibility on this page or null",
            "source_location": "paragraph/line/source clue or null",
            "confidence": 0.85
        }
    ],
    "places": [
        {
            "name": "raw place mention",
            "place_type": "court|property|incident|address|jurisdiction|other",
            "state": "state name or null",
            "district": "district name or null",
            "raw_text_span": "short source snippet or null",
            "mention_count": 1
        }
    ],
    "confidence": 0.85
}

Focus on:
- Legal precision (don't oversimplify complex legal concepts)
- Context preservation (maintain relationships between facts and rulings)
- Actionable insights (what matters for implementation)
- Direct evidence (prefer direct quotes over paraphrasing)"""

    def _build_user_prompt(self, page_num: int, page_text: str, total_pages: int) -> str:
        """User prompt for specific page analysis."""
        return f"""Analyze this page ({page_num}/{total_pages}) of a court judgment:

{page_text}

Extract page summary, key points, highlights, entities, dates, directions, departments, and places as JSON.
Remember: Legal precision is critical. Don't lose context."""

    async def _call_openai(self, system: str, user: str) -> dict[str, Any]:
        """Call OpenAI API for page analysis."""
        try:
            from openai import AsyncOpenAI
        except ImportError:
            raise ImportError("openai package required for OpenAI provider")

        try:
            client = AsyncOpenAI(api_key=self.api_key)
            response = await client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=self.temperature,
                max_tokens=2400,
            )

            content = response.choices[0].message.content
            result = json.loads(content)
            return result

        except json.JSONDecodeError as exc:
            logger.error("OpenAI returned invalid JSON: %s", type(exc).__name__)
            raise ValueError("AI response was not valid JSON")

    async def _call_anthropic(self, system: str, user: str) -> dict[str, Any]:
        """Call Anthropic API for page analysis."""
        try:
            from anthropic import Anthropic
        except ImportError:
            raise ImportError("anthropic package required for Anthropic provider")

        try:
            client = Anthropic(api_key=self.api_key)
            response = client.messages.create(
                model=self.model,
                max_tokens=2400,
                system=system,
                messages=[{"role": "user", "content": user}],
            )

            content = response.content[0].text
            result = json.loads(content)
            return result

        except json.JSONDecodeError as exc:
            logger.error("Anthropic returned invalid JSON: %s", type(exc).__name__)
            raise ValueError("AI response was not valid JSON")

    async def _call_gemini(self, system: str, user: str) -> dict[str, Any]:
        """Call shared Gemini client for page analysis."""
        api_key = self.api_key or settings.orderflow_ai_gemini_api_key
        if not api_key:
            raise ValueError("Missing Gemini API key for page summary extraction")

        response = call_gemini_json(
            api_key=api_key,
            model=self.model or settings.orderflow_ai_default_model,
            prompt=f"{system}\n\n{user}",
            temperature=self.temperature,
            max_output_tokens=settings.orderflow_ai_gemini_max_output_tokens,
            request_label="page summary extraction",
        )
        content = extract_gemini_text(response)
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            logger.error("Gemini returned invalid page summary JSON: %s", type(exc).__name__)
            raise ValueError("AI response was not valid JSON") from exc

    async def _ai_extract_places_only(
        self,
        *,
        page_num: int,
        page_text: str,
        state_hint: str | None,
        district_hint: str | None,
    ) -> dict[str, Any]:
        system_prompt = self._build_places_system_prompt()
        user_prompt = self._build_places_user_prompt(
            page_num=page_num,
            page_text=page_text,
            state_hint=state_hint,
            district_hint=district_hint,
        )

        if self.ai_provider == "openai":
            return await self._call_openai(system_prompt, user_prompt)
        if self.ai_provider == "anthropic":
            return await self._call_anthropic(system_prompt, user_prompt)
        if self.ai_provider == "gemini":
            return await self._call_gemini(system_prompt, user_prompt)
        return {"places": []}

    def _build_places_system_prompt(self) -> str:
        return """You are a legal document analyst extracting map-ready places.
Return strict JSON only:
{
  "places": [
    {
      "name": "raw place mention",
      "place_type": "court|property|incident|address|jurisdiction|other",
      "state": "state name or null",
      "district": "district name or null",
      "raw_text_span": "short source snippet or null",
      "mention_count": 1
    }
  ]
}

Rules:
- Identify Indian places that physically exist and could be plotted on a map.
- Include courts, cities, districts, property addresses, incident sites, and jurisdictions.
- Skip abstract references such as "petitioner's residence" without a town or address.
- Prefer the most specific form available.
- Return each same-place mention once with mention_count set to its page count."""

    def _build_places_user_prompt(
        self,
        *,
        page_num: int,
        page_text: str,
        state_hint: str | None,
        district_hint: str | None,
    ) -> str:
        hints = []
        if state_hint:
            hints.append(f"State hint: {state_hint}")
        if district_hint:
            hints.append(f"District hint: {district_hint}")
        hint_text = "\n".join(hints) if hints else "No metadata hints available."
        return f"""Extract map-ready places from page {page_num}.

{hint_text}

Page text:
{page_text[: settings.orderflow_ai_gemini_page_insight_prompt_chars]}"""

    def _deterministic_extract_page(self, page_text: str) -> dict[str, Any]:
        """
        Fallback deterministic extraction without AI.
        Useful for testing and when AI fails.
        """
        # Split into sentences
        sentences = re.split(r"[.!?]+", page_text)[:3]
        summary = ".".join(sentences).strip()

        # Simple keyword extraction for key points
        key_points = []
        patterns = [
            r"(The court .*?\.)",
            r"(It is .*?\.)",
            r"(Accordingly .*?\.)",
            r"(Therefore .*?\.)",
        ]

        for pattern in patterns:
            matches = re.findall(pattern, page_text, re.IGNORECASE)
            key_points.extend(matches[:2])

        key_points = key_points[:5]

        return {
            "summary": summary if summary else "Analysis of judgment page.",
            "key_points": key_points if key_points else ["No explicit key points extracted."],
            "highlights": [],
            "entities": self._deterministic_entities(page_text),
            "dates": self._deterministic_dates(page_text),
            "directions": self._deterministic_directions(page_text),
            "departments": self._deterministic_departments(page_text),
            "places": [],
            "confidence": 0.3,  # Low confidence for fallback
        }

    def _deterministic_entities(self, page_text: str) -> list[dict[str, Any]]:
        entities: list[dict[str, Any]] = []
        patterns = (
            (r"\b(?:petitioner|appellant)\s+([A-Z][A-Za-z .]{2,80})", "petitioner"),
            (r"\b(?:respondent)\s+([A-Z][A-Za-z .]{2,80})", "respondent"),
            (r"\b(?:High Court|Supreme Court|District Court)[A-Za-z ,.'-]{0,80}", "court"),
        )
        for pattern, entity_type in patterns:
            for match in re.finditer(pattern, page_text, re.IGNORECASE):
                entities.append(
                    {
                        "name": match.group(0).strip(" ,.;:"),
                        "entity_type": entity_type,
                        "role": None,
                        "source_location": "deterministic_text_match",
                        "confidence": 0.35,
                    }
                )
                if len(entities) >= 8:
                    return entities
        return entities

    def _deterministic_dates(self, page_text: str) -> list[dict[str, Any]]:
        dates: list[dict[str, Any]] = []
        pattern = re.compile(
            r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{1,2}\s+"
            r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
            r"\s+\d{4}|\d+\s+days?)\b",
            re.IGNORECASE,
        )
        for match in pattern.finditer(page_text):
            dates.append(
                {
                    "date_text": match.group(0),
                    "label": "timeline",
                    "source_location": "deterministic_text_match",
                    "is_inferred": False,
                    "confidence": 0.35,
                }
            )
            if len(dates) >= 8:
                break
        return dates

    def _deterministic_directions(self, page_text: str) -> list[dict[str, Any]]:
        directions: list[dict[str, Any]] = []
        for sentence in re.split(r"(?<=[.!?])\s+", page_text):
            if re.search(r"\b(direct|ordered|shall|must|comply|submit|file)\b", sentence, re.I):
                directions.append(
                    {
                        "direction_text": sentence.strip()[:500],
                        "source_location": "deterministic_sentence_match",
                        "directive_kind": "mandatory",
                        "compliance_required": "yes",
                        "confidence": 0.35,
                    }
                )
                if len(directions) >= 6:
                    break
        return directions

    def _deterministic_departments(self, page_text: str) -> list[dict[str, Any]]:
        departments: list[dict[str, Any]] = []
        for match in re.finditer(r"\b[A-Z][A-Za-z &]{2,60}\s+Department\b", page_text):
            departments.append(
                {
                    "name": match.group(0).strip(),
                    "role": None,
                    "source_location": "deterministic_text_match",
                    "confidence": 0.35,
                }
            )
            if len(departments) >= 6:
                break
        return departments

    def _deterministic_place_candidates(
        self,
        page_text: str,
        *,
        state_hint: str | None,
        district_hint: str | None,
    ) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []

        for match in re.finditer(
            r"\b(?:High Court of|District Court(?: at| of)?|Court of)\s+([A-Z][A-Za-z\s]{2,60})",
            page_text,
        ):
            candidates.append(
                {
                    "name": match.group(0).strip(" ,.;:"),
                    "place_type": "court",
                    "state": state_hint,
                    "district": district_hint,
                    "raw_text_span": _snippet(page_text, match.start(), match.end()),
                    "mention_count": 1,
                }
            )

        for place_name in (*_KNOWN_INDIAN_PLACE_NAMES, *_KNOWN_INDIAN_STATES):
            pattern = re.compile(rf"\b{re.escape(place_name)}\b", re.IGNORECASE)
            for match in pattern.finditer(page_text):
                matched_name = match.group(0)
                candidates.append(
                    {
                        "name": matched_name,
                        "place_type": "jurisdiction",
                        "state": matched_name if place_name in _KNOWN_INDIAN_STATES else state_hint,
                        "district": district_hint,
                        "raw_text_span": _snippet(page_text, match.start(), match.end()),
                        "mention_count": 1,
                    }
                )

        return candidates

    def _find_context_links(
        self,
        page_num: int,
        page_text: str,
        all_pages: dict[int, str],
    ) -> list[dict[str, Any]]:
        """
        Find references to other pages (explicit and thematic).

        Returns:
            List of {page_number, reason} dicts
        """
        links = []

        # 1. Explicit page references
        page_refs = re.findall(
            r"(?:page|p\.(?:\.)?|pages?|at\s+p)\s+(\d+)",
            page_text,
            re.IGNORECASE,
        )

        for ref_str in set(page_refs):
            try:
                ref_num = int(ref_str)
                max_page = max(all_pages.keys())
                if 1 <= ref_num <= max_page and ref_num != page_num:
                    links.append(
                        {
                            "page_number": ref_num,
                            "reason": f"explicit reference to page {ref_num}",
                        }
                    )
            except (ValueError, IndexError):
                pass

        # 2. Thematic linking (shared keywords)
        page_keywords = set(page_text.lower().split())
        keyword_threshold = 10  # Minimum overlap to link pages

        for other_page_num in sorted(all_pages.keys()):
            if other_page_num == page_num:
                continue

            other_text = all_pages[other_page_num]
            other_keywords = set(other_text.lower().split())
            overlap = len(page_keywords & other_keywords)

            if overlap > keyword_threshold:
                # Avoid duplicates
                if not any(link["page_number"] == other_page_num for link in links):
                    links.append(
                        {
                            "page_number": other_page_num,
                            "reason": "related discussion/evidence",
                        }
                    )

        # Limit to top 3 most relevant
        return links[:3]
