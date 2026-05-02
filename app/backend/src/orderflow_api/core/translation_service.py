"""Translation service for multi-language document support.

Provides translation capabilities via LibreTranslate with caching and retry logic.
Translates from any language to English (for extraction) and back to source language (for export).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import Optional

import aiohttp
from tenacity import (
    before_sleep_log,
    retry,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)


class TranslationServiceConfig:
    """Configuration for LibreTranslate service."""

    def __init__(
        self,
        service_url: str = "http://localhost:5000",
        api_key: str | None = None,
        timeout_seconds: int = 30,
        max_retries: int = 3,
    ):
        """Initialize translation service config.

        Args:
            service_url: Base URL of LibreTranslate service (default: localhost:5000).
            api_key: Optional API key if LibreTranslate requires authentication.
            timeout_seconds: Request timeout in seconds (default: 30).
            max_retries: Maximum retry attempts for failed requests (default: 3).
        """
        self.service_url = service_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries


class TranslationService:
    """Service for translating text using LibreTranslate.

    Includes caching to avoid re-translating identical text.
    """

    def __init__(
        self,
        config: TranslationServiceConfig,
        cache_backend: Optional[object] = None,
    ):
        """Initialize translation service.

        Args:
            config: TranslationServiceConfig instance.
            cache_backend: Optional Redis or similar cache backend for caching translations.
                           Should implement get/set with key expiry.
        """
        self.config = config
        self.cache_backend = cache_backend

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    async def translate(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
        use_cache: bool = True,
    ) -> str:
        """Translate text from source language to target language.

        Args:
            text: Text to translate.
            source_lang: ISO 639-1 source language code (e.g., 'hi').
            target_lang: ISO 639-1 target language code (e.g., 'en').
            use_cache: Whether to use caching (default: True).

        Returns:
            Translated text.

        Raises:
            TranslationServiceError: If translation fails after retries.
        """
        # If source and target are the same, return original
        if source_lang == target_lang:
            return text

        if not text or len(text.strip()) == 0:
            return text

        # Try cache first
        if use_cache and self.cache_backend:
            cache_key = self._make_cache_key(text, source_lang, target_lang)
            cached_result = await self._get_from_cache(cache_key)
            if cached_result:
                logger.info(
                    f"Translation cache hit: {source_lang}→{target_lang} ({len(text)} chars)"
                )
                return cached_result

        # Perform translation
        try:
            translated_text = await self._call_libretranslate(text, source_lang, target_lang)
            logger.info(
                f"Translation completed: {source_lang}→{target_lang} "
                f"({len(text)} → {len(translated_text)} chars)"
            )

            # Cache result
            if use_cache and self.cache_backend:
                cache_key = self._make_cache_key(text, source_lang, target_lang)
                await self._set_in_cache(cache_key, translated_text, ttl=86400)  # 24h TTL

            return translated_text

        except Exception as e:
            logger.error(
                f"Translation failed for {source_lang}→{target_lang}: {e}. "
                f"Returning original text."
            )
            raise TranslationServiceError(
                f"Failed to translate from {source_lang} to {target_lang}: {str(e)}"
            ) from e

    async def translate_batch(
        self,
        texts: list[str],
        source_lang: str,
        target_lang: str,
        use_cache: bool = True,
    ) -> list[str]:
        """Translate a batch of texts.

        Args:
            texts: List of texts to translate.
            source_lang: ISO 639-1 source language code.
            target_lang: ISO 639-1 target language code.
            use_cache: Whether to use caching (default: True).

        Returns:
            List of translated texts in the same order.
        """
        results = []
        for text in texts:
            translated = await self.translate(text, source_lang, target_lang, use_cache)
            results.append(translated)
        return results

    async def _call_libretranslate(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
    ) -> str:
        """Call LibreTranslate API to perform translation.

        Args:
            text: Text to translate.
            source_lang: Source language code.
            target_lang: Target language code.

        Returns:
            Translated text.

        Raises:
            TranslationServiceError: If API call fails.
        """
        url = f"{self.config.service_url}/translate"
        payload = {
            "q": text,
            "source": source_lang,
            "target": target_lang,
        }

        if self.config.api_key:
            payload["api_key"] = self.config.api_key

        headers = {"Content-Type": "application/json"}
        timeout = aiohttp.ClientTimeout(total=self.config.timeout_seconds)

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload, headers=headers) as response:
                    return await self._parse_translation_response(response)

        except asyncio.TimeoutError as e:
            raise TranslationServiceError(f"Translation request timed out: {str(e)}") from e
        except aiohttp.ClientError as e:
            raise TranslationServiceError(f"HTTP client error during translation: {str(e)}") from e

    async def _parse_translation_response(self, response: object) -> str:
        status = getattr(response, "status", None)
        if status != 200:
            error_text = await response.text()
            raise TranslationServiceError(f"LibreTranslate returned {status}: {error_text}")

        data = await response.json()
        translated_text = data.get("translatedText", "")
        if not translated_text:
            raise TranslationServiceError("Empty translation result from LibreTranslate")
        return translated_text

    def _make_cache_key(self, text: str, source_lang: str, target_lang: str) -> str:
        """Generate a cache key for a translation.

        Args:
            text: Text to translate.
            source_lang: Source language code.
            target_lang: Target language code.

        Returns:
            Cache key.
        """
        text_hash = hashlib.sha256(text.encode()).hexdigest()[:16]
        return f"translation:{source_lang}:{target_lang}:{text_hash}"

    async def _get_from_cache(self, cache_key: str) -> str | None:
        """Retrieve value from cache.

        Args:
            cache_key: Cache key.

        Returns:
            Cached value or None if not found.
        """
        if not self.cache_backend:
            return None

        try:
            # Support both async and sync cache backends
            if hasattr(self.cache_backend, "get"):
                if hasattr(self.cache_backend.get, "__await__"):
                    value = await self.cache_backend.get(cache_key)
                else:
                    value = self.cache_backend.get(cache_key)
                if isinstance(value, bytes):
                    return value.decode()
                return value
        except Exception as e:
            logger.warning(f"Cache get failed: {e}")

        return None

    async def _set_in_cache(self, cache_key: str, value: str, ttl: int = 86400) -> None:
        """Store value in cache.

        Args:
            cache_key: Cache key.
            value: Value to cache.
            ttl: Time to live in seconds (default: 24 hours).
        """
        if not self.cache_backend:
            return

        try:
            # Support both async and sync cache backends
            if hasattr(self.cache_backend, "set"):
                if hasattr(self.cache_backend.set, "__await__"):
                    await self.cache_backend.set(cache_key, value, ex=ttl)
                else:
                    self.cache_backend.set(cache_key, value, ex=ttl)
        except Exception as e:
            logger.warning(f"Cache set failed: {e}")


class TranslationServiceError(Exception):
    """Exception raised when translation service encounters an error."""

    pass
