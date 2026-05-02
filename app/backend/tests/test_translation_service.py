"""Unit tests for translation service."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from orderflow_api.core.translation_service import (
    TranslationService,
    TranslationServiceConfig,
    TranslationServiceError,
)


@pytest.fixture
def translation_config():
    """Create a translation service config."""
    return TranslationServiceConfig(
        service_url="http://localhost:5000",
        timeout_seconds=10,
        max_retries=2,
    )


@pytest.fixture
def translation_service(translation_config):
    """Create a translation service with mocked cache."""
    mock_cache = MagicMock()
    return TranslationService(config=translation_config, cache_backend=mock_cache)


class TestTranslationService:
    """Test translation service functionality."""

    @pytest.mark.asyncio
    async def test_translate_same_language_returns_original(self, translation_service):
        """Test that translating to same language returns original text."""
        text = "This is English text"
        result = await translation_service.translate(text, "en", "en")
        assert result == text

    @pytest.mark.asyncio
    async def test_translate_empty_text_returns_empty(self, translation_service):
        """Test that translating empty text returns empty string."""
        result = await translation_service.translate("", "en", "hi")
        assert result == ""

        result = await translation_service.translate("   ", "en", "hi")
        assert result == "   "

    @patch("orderflow_api.core.translation_service.aiohttp.ClientSession")
    @pytest.mark.asyncio
    async def test_translate_calls_libretranslate_api(self, mock_session_class, translation_service):
        """Test that translation calls LibreTranslate API correctly."""
        # Mock the HTTP response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = {
            "translatedText": "यह अंग्रेजी पाठ है"
        }

        mock_session = AsyncMock()
        mock_session.__aenter__.return_value = mock_session
        mock_session.post.return_value.__aenter__.return_value = mock_response

        mock_session_class.return_value = mock_session

        # Call translation
        text = "This is English text"
        result = await translation_service.translate(text, "en", "hi", use_cache=False)

        assert result == "यह अंग्रेजी पाठ है"

        # Verify API was called correctly
        mock_session.post.assert_called_once()
        call_args = mock_session.post.call_args
        assert "http://localhost:5000/translate" in str(call_args)

    @patch("orderflow_api.core.translation_service.aiohttp.ClientSession")
    @pytest.mark.asyncio
    async def test_translate_api_error_raises_exception(self, mock_session_class, translation_service):
        """Test that API errors raise TranslationServiceError."""
        # Mock a failed response
        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.text.return_value = "Internal Server Error"

        mock_session = AsyncMock()
        mock_session.__aenter__.return_value = mock_session
        mock_session.post.return_value.__aenter__.return_value = mock_response

        mock_session_class.return_value = mock_session

        # Call translation - should raise after retries
        with pytest.raises(TranslationServiceError):
            await translation_service.translate("Test", "en", "hi", use_cache=False)

    @patch("orderflow_api.core.translation_service.aiohttp.ClientSession")
    @pytest.mark.asyncio
    async def test_translate_batch(self, mock_session_class, translation_service):
        """Test batch translation."""
        # Mock responses for each text
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.side_effect = [
            {"translatedText": "अनुवाद 1"},
            {"translatedText": "अनुवाद 2"},
            {"translatedText": "अनुवाद 3"},
        ]

        mock_session = AsyncMock()
        mock_session.__aenter__.return_value = mock_session
        mock_session.post.return_value.__aenter__.return_value = mock_response

        mock_session_class.return_value = mock_session

        texts = ["Text 1", "Text 2", "Text 3"]
        results = await translation_service.translate_batch(texts, "en", "hi", use_cache=False)

        assert len(results) == 3
        assert results == ["अनुवाद 1", "अनुवाद 2", "अनुवाद 3"]

    @pytest.mark.asyncio
    async def test_translate_with_cache_hit(self, translation_service):
        """Test that cached translation is returned without API call."""
        translation_service.cache_backend.get.return_value = "cached_translation"
        translation_service._get_from_cache = AsyncMock(return_value="cached_translation")

        text = "Test text"
        result = await translation_service.translate(text, "en", "hi", use_cache=True)

        assert result == "cached_translation"

    @pytest.mark.asyncio
    async def test_translate_with_cache_miss_and_store(self, translation_service):
        """Test that translation result is cached for future use."""
        # Mock cache miss
        translation_service._get_from_cache = AsyncMock(return_value=None)
        translation_service._set_in_cache = AsyncMock()

        with patch("orderflow_api.core.translation_service.aiohttp.ClientSession") as mock_session_class:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json.return_value = {"translatedText": "translated"}

            mock_session = AsyncMock()
            mock_session.__aenter__.return_value = mock_session
            mock_session.post.return_value.__aenter__.return_value = mock_response

            mock_session_class.return_value = mock_session

            text = "Test text"
            result = await translation_service.translate(text, "en", "hi", use_cache=True)

            assert result == "translated"
            # Verify cache was set
            translation_service._set_in_cache.assert_called_once()

    def test_cache_key_generation(self, translation_service):
        """Test that cache keys are generated consistently."""
        text = "Test text for caching"
        key1 = translation_service._make_cache_key(text, "en", "hi")
        key2 = translation_service._make_cache_key(text, "en", "hi")

        # Same text, language pair should generate same key
        assert key1 == key2

        # Different languages should generate different keys
        key3 = translation_service._make_cache_key(text, "en", "ta")
        assert key1 != key3

    def test_translation_service_config(self):
        """Test TranslationServiceConfig initialization."""
        config = TranslationServiceConfig(
            service_url="http://example.com:5000",
            api_key="test-key",
            timeout_seconds=20,
            max_retries=5,
        )
        assert config.service_url == "http://example.com:5000"
        assert config.api_key == "test-key"
        assert config.timeout_seconds == 20
        assert config.max_retries == 5

    def test_translation_service_config_url_cleanup(self):
        """Test that TranslationServiceConfig cleans up trailing slashes."""
        config = TranslationServiceConfig(service_url="http://example.com/")
        assert config.service_url == "http://example.com"


class TestTranslationServiceError:
    """Test TranslationServiceError exception."""

    def test_translation_service_error_is_exception(self):
        """Test that TranslationServiceError is an Exception."""
        error = TranslationServiceError("Test error")
        assert isinstance(error, Exception)
        assert str(error) == "Test error"
