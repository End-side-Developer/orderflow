"""Unit tests for language detection service."""

from __future__ import annotations

from orderflow_api.core.language_service import (
    detect_language,
    get_language_name,
    is_language_supported,
    SUPPORTED_LANGUAGES,
)


class TestLanguageDetection:
    """Test language detection functionality."""

    def test_detect_english_text(self):
        """Test detection of English text."""
        english_text = """
        This is a court judgment. The judge orders the defendant to pay damages
        to the plaintiff. The order shall be executed within 30 days from the date
        of this judgment. Any appeal may be filed within 60 days.
        """
        result = detect_language(english_text)
        assert result.detected_language == "en"
        assert result.confidence > 0.8
        assert result.is_supported is True

    def test_detect_hindi_text(self):
        """Test detection of Hindi text."""
        hindi_text = """
        यह एक न्यायालय का निर्णय है। न्यायाधीश प्रतिवादी को वादी को नुकसान भुगतान करने का आदेश देते हैं।
        यह आदेश इस निर्णय की तारीख से 30 दिन के भीतर निष्पादित किया जाएगा।
        """
        result = detect_language(hindi_text)
        assert result.detected_language == "hi"
        assert result.confidence > 0.7
        assert result.is_supported is True

    def test_detect_tamil_text(self):
        """Test detection of Tamil text."""
        tamil_text = """
        இது ஒரு நீதிமன்ற தீர்ப்பு ஆகும். நீதியரசர் பிரதிவாதிக்கு வாதியின் இழப்பு ஈடுபெற
        வரிசைப்படுத்த ஆदेश கொடுக்கிறார். இந்த கட்டளை இந்த தீர்ப்பின் தேதியிலிருந்து 30 நாட்களுக்குள் செயல்படுத்தப்பட வேண்டும்.
        """
        result = detect_language(tamil_text)
        assert result.detected_language == "ta"
        assert result.confidence > 0.7
        assert result.is_supported is True

    def test_detect_telugu_text(self):
        """Test detection of Telugu text."""
        telugu_text = """
        ఇది ఒక కోర్టు తీర్పు. న్యాయమూర్తి ప్రతివాది వాది నష్టాల కోసం చెల్లించాలని ఆదేశిస్తారు.
        ఈ ఆదేశం ఈ తీర్పు నుండి 30 రోజుల్లో అమలు చేయాలి.
        """
        result = detect_language(telugu_text)
        assert result.detected_language == "te"
        assert result.confidence > 0.7
        assert result.is_supported is True

    def test_detect_kannada_text(self):
        """Test detection of Kannada text."""
        kannada_text = """
        ಇದು ಒಂದು ನ್ಯಾಯಾಲಯದ ತೀರ್ಪು. ನ್ಯಾಯಾಧಿಪತಿ ಪ್ರತಿವಾದಿಗೆ ವಾದಿಗೆ ನಷ್ಟದ ನಿಬಂಧನೆ ನೀಡುತ್ತಾರೆ.
        ಈ ಆದೇಶವನ್ನು ಈ ತೀರ್ಪಿನ ದಿನಾಂಕದಿಂದ 30 ದಿನಗಳಲ್ಲಿ ನಿರ್ವಾಹಿಸಬೇಕು.
        """
        result = detect_language(kannada_text)
        assert result.detected_language == "kn"
        assert result.confidence > 0.7
        assert result.is_supported is True

    def test_detect_malayalam_text(self):
        """Test detection of Malayalam text."""
        malayalam_text = """
        ഇത് കോടതിയുടെ ഒരു വിധിയാണ്. ജഡ്ജി പ്രതിക്കാരനെ കേസ് കൊടുക്കുന്നവനെ നാണ്കളഞ്ഞാണ് നിര്ദ്ദേശിക്കുന്നത്.
        ഈ കട്ടൊണ്ട് ഈ വിധിയുടെ തീയതിയില് നിന്ന് 30 ദിവസത്തിനകം നിര്വ്വഹിക്കുവാനാണ്.
        """
        result = detect_language(malayalam_text)
        assert result.detected_language == "ml"
        assert result.confidence > 0.7
        assert result.is_supported is True

    def test_detect_marathi_text(self):
        """Test detection of Marathi text."""
        marathi_text = """
        हा एक न्यायालयीन निर्णय आहे. न्यायाधीश प्रतिवादीला वादकरत्याला नुकसान भरपाई देण्याचा आदेश देतात.
        हा आदेश या निर्णयाच्या तारखेपासून 30 दिवसांत अंमलबजावणी करावा.
        """
        result = detect_language(marathi_text)
        assert result.detected_language == "mr"
        assert result.confidence > 0.7
        assert result.is_supported is True

    def test_detect_empty_text_uses_default(self):
        """Test that empty text returns default language."""
        result = detect_language("")
        assert result.detected_language == "en"
        assert result.confidence == 0.0
        assert result.is_supported is True

    def test_detect_short_text_uses_default(self):
        """Test that very short text returns default language."""
        result = detect_language("hi")
        assert result.detected_language == "en"
        assert result.confidence == 0.0

    def test_detect_with_custom_default(self):
        """Test detection with custom default language."""
        result = detect_language("", default_language="hi")
        assert result.detected_language == "hi"

    def test_mixed_language_text_detects_dominant(self):
        """Test that mixed language text detects dominant language."""
        # Mostly English with some Hindi words
        mixed_text = """
        यह एक कानूनी दस्तावेज़ है। The court hereby orders the defendant to pay
        damages to the plaintiff. यह आदेश अंतिम है।
        """
        result = detect_language(mixed_text)
        assert result.is_supported is True
        # Result should detect one of the languages
        assert result.detected_language in SUPPORTED_LANGUAGES


class TestLanguageNameAndSupport:
    """Test language name and support check functions."""

    def test_get_language_name_all_supported_languages(self):
        """Test that all supported languages have display names."""
        for lang_code, lang_name in SUPPORTED_LANGUAGES.items():
            result = get_language_name(lang_code)
            assert result == lang_name

    def test_get_language_name_unknown_language(self):
        """Test that unknown language returns formatted fallback."""
        result = get_language_name("xx")
        assert "Unknown" in result
        assert "xx" in result

    def test_is_language_supported_valid_languages(self):
        """Test that all supported languages are recognized."""
        for lang_code in SUPPORTED_LANGUAGES.keys():
            assert is_language_supported(lang_code) is True

    def test_is_language_supported_invalid_language(self):
        """Test that invalid languages are not supported."""
        assert is_language_supported("xx") is False
        assert is_language_supported("fr") is False
        assert is_language_supported("es") is False
        assert is_language_supported("") is False

    def test_supported_languages_constants(self):
        """Test that SUPPORTED_LANGUAGES constant has expected languages."""
        expected = {"en", "hi", "ta", "te", "kn", "ml", "mr"}
        assert set(SUPPORTED_LANGUAGES.keys()) == expected
