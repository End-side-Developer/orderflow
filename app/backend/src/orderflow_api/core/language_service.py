"""Language detection service for multi-language document support.

Detects the language of extracted text from court judgment PDFs.
Supports: English, Hindi, Tamil, Telugu, Kannada, Malayalam, Marathi.
"""

from __future__ import annotations

import logging
from typing import NamedTuple

import langdetect

logger = logging.getLogger(__name__)

# ISO 639-1 language codes
SUPPORTED_LANGUAGES = {
    "en": "English",
    "hi": "हिन्दी (Hindi)",
    "ta": "தமிழ் (Tamil)",
    "te": "తెలుగు (Telugu)",
    "kn": "ಕನ್ನಡ (Kannada)",
    "ml": "മലയാളം (Malayalam)",
    "mr": "मराठी (Marathi)",
}


class LanguageDetectionResult(NamedTuple):
    """Result of language detection."""

    detected_language: str
    """ISO 639-1 language code (e.g., 'hi', 'en')."""
    confidence: float
    """Confidence score between 0.0 and 1.0."""
    is_supported: bool
    """Whether the detected language is in the supported list."""


def detect_language(text: str, default_language: str = "en") -> LanguageDetectionResult:
    """Detect the language of text.

    Args:
        text: The text to analyze (preferably at least 50 characters for accuracy).
        default_language: Language code to return if detection fails (default: "en").

    Returns:
        LanguageDetectionResult with detected language, confidence, and support status.
    """
    if not text or len(text.strip()) < 10:
        logger.warning(
            f"Text too short for reliable detection ({len(text)} chars). "
            f"Defaulting to {default_language}"
        )
        return LanguageDetectionResult(
            detected_language=default_language,
            confidence=0.0,
            is_supported=default_language in SUPPORTED_LANGUAGES,
        )

    try:
        # langdetect returns probabilities; get the most likely language
        detected_lang = langdetect.detect(text)
        probs = langdetect.detect_langs(text)

        # Find the confidence score for the detected language
        confidence = next((p.prob for p in probs if p.lang == detected_lang), 0.0)

        is_supported = detected_lang in SUPPORTED_LANGUAGES

        logger.info(
            f"Language detected: {detected_lang} (confidence: {confidence:.3f}, supported: {is_supported})"
        )

        return LanguageDetectionResult(
            detected_language=detected_lang,
            confidence=float(confidence),
            is_supported=is_supported,
        )

    except langdetect.LangDetectException as e:
        logger.warning(f"Language detection failed: {e}. Defaulting to {default_language}")
        return LanguageDetectionResult(
            detected_language=default_language,
            confidence=0.0,
            is_supported=default_language in SUPPORTED_LANGUAGES,
        )


def get_language_name(language_code: str) -> str:
    """Get the display name for a language code.

    Args:
        language_code: ISO 639-1 language code (e.g., 'hi').

    Returns:
        Human-readable language name (e.g., 'हिन्दी (Hindi)').
    """
    return SUPPORTED_LANGUAGES.get(language_code, f"Unknown ({language_code})")


def is_language_supported(language_code: str) -> bool:
    """Check if a language code is supported for translation.

    Args:
        language_code: ISO 639-1 language code.

    Returns:
        True if language is supported, False otherwise.
    """
    return language_code in SUPPORTED_LANGUAGES
