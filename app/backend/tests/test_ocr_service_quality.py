from types import SimpleNamespace

from orderflow_api.api.ocr_service import (
    OcrPageResult,
    _better_ocr_result,
    _flatten_paddle_result,
    _ocr_result_is_usable,
    _paddle_language_candidates,
    _tesseract_boxes_and_confidence,
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


def test_paddle_result_exposes_normalized_line_boxes() -> None:
    raw = [
        {
            "res": {
                "rec_texts": ["Submit report", "within 30 days"],
                "rec_scores": [0.91, 0.83],
                "rec_boxes": [[10, 20, 210, 50], [12, 60, 190, 90]],
            }
        }
    ]

    lines, confidences, boxes = _flatten_paddle_result(
        raw,
        image_width=400,
        image_height=200,
    )

    assert lines == ["Submit report", "within 30 days"]
    assert confidences == [0.91, 0.83]
    assert boxes[0]["bbox"] == {"left": 0.025, "top": 0.1, "width": 0.5, "height": 0.15}
    assert boxes[0]["granularity"] == "line"


def test_tesseract_tsv_exposes_word_boxes(monkeypatch) -> None:
    class Completed:
        stdout = (
            "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
            "5\t1\t1\t1\t1\t1\t20\t40\t80\t20\t92\tSubmit\n"
            "5\t1\t1\t1\t1\t2\t110\t40\t60\t20\t88\treport\n"
        )

    monkeypatch.setattr(
        "orderflow_api.api.ocr_service.subprocess.run",
        lambda *args, **kwargs: Completed(),
    )
    monkeypatch.setattr(
        "orderflow_api.api.ocr_service._image_dimensions",
        lambda image_path: (400.0, 200.0),
    )

    boxes, confidence = _tesseract_boxes_and_confidence("tesseract", "page.png", "eng")

    assert confidence == 0.9
    assert boxes[0]["text"] == "Submit"
    assert boxes[0]["bbox"] == {"left": 0.05, "top": 0.2, "width": 0.2, "height": 0.1}
    assert boxes[0]["granularity"] == "word"
