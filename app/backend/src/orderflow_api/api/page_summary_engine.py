"""
Page-by-page summary extraction engine.

Generates AI-powered summaries of court judgment pages, preserving
legal context and identifying critical decision points.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from orderflow_api.schemas.page_summaries import (
    ContextLink,
    HighlightItem,
    PageSummaryRecord,
)

logger = logging.getLogger(__name__)


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
    ) -> list[PageSummaryRecord]:
        """
        Extract summaries for all pages.

        Args:
            document_id: Document UUID
            pages: {page_number: page_text}
            obligations: {page_number: [obligation_ids]} (optional)

        Returns:
            List of PageSummaryRecord objects ordered by page number
        """
        if obligations is None:
            obligations = {}

        summaries = []
        total_pages = len(pages)

        for page_num in sorted(pages.keys()):
            page_text = pages[page_num]

            try:
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

                # Create summary record
                summary_record = PageSummaryRecord(
                    id=uuid4(),
                    document_id=document_id,
                    page_number=page_num,
                    page_text=page_text,
                    summary=extraction.get("summary", ""),
                    key_points=extraction.get("key_points", []),
                    important_highlights=[
                        HighlightItem(**h)
                        for h in extraction.get("highlights", [])
                    ],
                    context_links=[ContextLink(**link) for link in context_links],
                    obligation_ids=page_obligations,
                    confidence=extraction.get("confidence", 0.85),
                    extraction_mode="ai",
                    ai_model=self.model,
                    ai_provider=self.ai_provider,
                    generated_at=datetime.utcnow(),
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )

                summaries.append(summary_record)
                logger.info(
                    f"Extracted summary for page {page_num}/{total_pages}",
                    extra={"document_id": str(document_id)},
                )

            except Exception as e:
                logger.error(
                    f"Failed to extract summary for page {page_num}: {e}",
                    extra={"document_id": str(document_id)},
                )
                # Continue with next page on error
                continue

        return summaries

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
            else:
                raise ValueError(f"Unsupported AI provider: {self.ai_provider}")
        except Exception as e:
            logger.error(f"AI extraction failed: {e}")
            # Fallback to deterministic extraction
            return self._deterministic_extract_page(page_text)

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

Extract summary, key points, and important highlights as JSON.
Remember: Legal precision is critical. Don't lose context."""

    async def _call_openai(self, system: str, user: str) -> dict[str, Any]:
        """Call OpenAI API for page analysis."""
        try:
            import openai
        except ImportError:
            raise ImportError("openai package required for OpenAI provider")

        try:
            response = await openai.ChatCompletion.acreate(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=self.temperature,
                max_tokens=1500,
            )

            content = response.choices[0].message.content
            result = json.loads(content)
            return result

        except json.JSONDecodeError as e:
            logger.error(f"OpenAI returned invalid JSON: {e}")
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
                max_tokens=1500,
                system=system,
                messages=[{"role": "user", "content": user}],
            )

            content = response.content[0].text
            result = json.loads(content)
            return result

        except json.JSONDecodeError as e:
            logger.error(f"Anthropic returned invalid JSON: {e}")
            raise ValueError("AI response was not valid JSON")

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
            "confidence": 0.3,  # Low confidence for fallback
        }

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
                if not any(
                    link["page_number"] == other_page_num for link in links
                ):
                    links.append(
                        {
                            "page_number": other_page_num,
                            "reason": "related discussion/evidence",
                        }
                    )

        # Limit to top 3 most relevant
        return links[:3]
