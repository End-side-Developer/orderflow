from types import SimpleNamespace

from orderflow_api.api.ocr_service import (
    OcrPageResult,
    _better_ocr_result,
    _ocr_result_is_usable,
    _paddle_language_candidates,
)


def test_default_language_ocr_compares_english_and_devanagari_models() -> None:
    assert _paddle_language_candidates("en") == ["en", "mr", "hi"]
    assert _paddle_language_candidates(None) == ["en", "mr", "hi"]


def test_marathi_ocr_rejects_latin_garbage_even_when_confident() -> None:
    settings = SimpleNamespace(orderflow_ocr_min_chars=20, orderflow_ocr_min_confidence=0.55)
    result = OcrPageResult(
        text="2lEre Eelt plizh lielnbjh enelt uekg Has3a loa anux GgR 3",
        engine="paddleocr",
        engine_version="3.5.0",
        language_hint="mr",
        confidence=0.96,
        page_number=1,
        duration_ms=1000,
    )

    assert not _ocr_result_is_usable(result, settings)


def test_devanagari_candidate_beats_corrupted_english_candidate() -> None:
    marathi = OcrPageResult(
        text=(
            "\u092e\u0941\u0902\u092c\u0908 \u0909\u091a\u094d\u091a "
            "\u0928\u094d\u092f\u093e\u092f\u093e\u0932\u092f, "
            "\u0928\u093e\u0917\u092a\u0942\u0930 \u0916\u0902\u0921\u092a\u0940\u0920"
        ),
        engine="paddleocr",
        engine_version="3.5.0",
        language_hint="mr",
        confidence=0.86,
        page_number=1,
        duration_ms=1200,
    )
    corrupted_english = OcrPageResult(
        text="2lEre Eelt plizh lielnbjh enelt uekg Has3a loa anux GgR 3",
        engine="paddleocr",
        engine_version="3.5.0",
        language_hint="en",
        confidence=0.96,
        page_number=1,
        duration_ms=1100,
    )

    assert _better_ocr_result(marathi, corrupted_english)
