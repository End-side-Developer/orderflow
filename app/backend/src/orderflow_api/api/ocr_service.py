from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import importlib.metadata
import os
import re
import statistics
import subprocess
import time
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any


@dataclass(frozen=True)
class OcrPageResult:
    text: str
    engine: str | None
    engine_version: str | None
    language_hint: str | None
    confidence: float | None
    page_number: int
    duration_ms: int
    error: str | None = None
    orientation_degrees: int = 0
    boxes: tuple[dict[str, Any], ...] = ()

    @property
    def succeeded(self) -> bool:
        return bool(self.text.strip()) and self.error is None


class OcrUnavailableError(RuntimeError):
    """Raised when a configured OCR engine is unavailable at runtime."""


_COMMON_ENGLISH_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "case",
    "court",
    "for",
    "from",
    "has",
    "have",
    "in",
    "is",
    "it",
    "no",
    "not",
    "of",
    "on",
    "or",
    "page",
    "petition",
    "police",
    "respondent",
    "state",
    "that",
    "the",
    "this",
    "to",
    "was",
    "were",
    "with",
}


def extract_pdf_page_with_ocr(
    *,
    payload: bytes,
    page_number: int,
    source_language: str | None,
    settings: Any,
) -> OcrPageResult:
    started = time.perf_counter()
    if not getattr(settings, "orderflow_ocr_enabled", True):
        return _failure(page_number, started, "disabled", source_language, "ocr_disabled")

    image_path: Path | None = None
    errors: list[str] = []
    try:
        image_path = _render_pdf_page(payload, page_number, _ocr_dpi(settings))
        for engine in _engine_plan(settings):
            try:
                result = _run_engine(
                    engine=engine,
                    image_path=image_path,
                    page_number=page_number,
                    source_language=source_language,
                    settings=settings,
                    started=started,
                )
            except Exception as exc:
                errors.append(f"{engine}:{exc.__class__.__name__}")
                continue
            if _ocr_result_is_usable(result, settings):
                return result
            errors.append(f"{engine}:low_confidence_or_short_text")
        return _failure(
            page_number,
            started,
            ",".join(_engine_plan(settings)) or "none",
            source_language,
            ";".join(errors) or "no_ocr_engine_succeeded",
        )
    except Exception as exc:
        return _failure(
            page_number,
            started,
            ",".join(_engine_plan(settings)) or "none",
            source_language,
            f"render_or_ocr_failed:{exc.__class__.__name__}",
        )
    finally:
        if image_path is not None:
            image_path.unlink(missing_ok=True)


def _render_pdf_page(payload: bytes, page_number: int, dpi: int) -> Path:
    try:
        import pypdfium2 as pdfium
    except Exception as exc:
        raise OcrUnavailableError("pypdfium2_unavailable") from exc

    pdf_path: Path | None = None
    image_path: Path | None = None
    document: Any | None = None
    page: Any | None = None
    bitmap: Any | None = None
    try:
        with NamedTemporaryFile(delete=False, suffix=".pdf") as pdf_file:
            pdf_file.write(payload)
            pdf_path = Path(pdf_file.name)
        with NamedTemporaryFile(delete=False, suffix=".png") as image_file:
            image_path = Path(image_file.name)

        document = pdfium.PdfDocument(str(pdf_path))
        page_index = max(0, page_number - 1)
        if page_index >= len(document):
            raise ValueError("page_number_out_of_range")
        page = document[page_index]
        bitmap = page.render(scale=max(1.0, dpi / 72.0))
        _save_prepared_ocr_image(bitmap.to_pil(), image_path)
        return image_path
    except Exception:
        if image_path is not None:
            image_path.unlink(missing_ok=True)
        raise
    finally:
        _close_pdfium_handle(bitmap)
        _close_pdfium_handle(page)
        _close_pdfium_handle(document)
        if pdf_path is not None:
            pdf_path.unlink(missing_ok=True)


def _close_pdfium_handle(handle: Any | None) -> None:
    if handle is None:
        return
    close = getattr(handle, "close", None)
    if callable(close):
        try:
            close()
        except Exception:
            pass


def _save_prepared_ocr_image(image: Any, image_path: Path) -> None:
    try:
        from PIL import ImageOps
    except Exception as exc:
        raise OcrUnavailableError("pillow_unavailable") from exc

    with image:
        prepared = ImageOps.autocontrast(image.convert("RGB"))
        max_side = _ocr_image_max_side()
        if max(prepared.size) > max_side:
            prepared.thumbnail((max_side, max_side))
        prepared.save(image_path)


def _ocr_image_max_side() -> int:
    try:
        value = int(os.environ.get("ORDERFLOW_OCR_IMAGE_MAX_SIDE", "2200"))
    except ValueError:
        value = 2200
    return min(3500, max(1200, value))


def _run_engine(
    *,
    engine: str,
    image_path: Path,
    page_number: int,
    source_language: str | None,
    settings: Any,
    started: float,
) -> OcrPageResult:
    normalized = engine.strip().lower()
    if normalized == "paddleocr":
        return _run_paddleocr(
            image_path=image_path,
            page_number=page_number,
            source_language=source_language,
            started=started,
        )
    if normalized == "tesseract":
        return _run_tesseract(
            image_path=image_path,
            page_number=page_number,
            source_language=source_language,
            settings=settings,
            started=started,
        )
    raise OcrUnavailableError(f"unsupported_ocr_engine:{engine}")


def _run_paddleocr(
    *,
    image_path: Path,
    page_number: int,
    source_language: str | None,
    started: float,
) -> OcrPageResult:
    _ensure_paddlex_cache_home()
    best_result: OcrPageResult | None = None
    for language_hint in _paddle_language_candidates(source_language):
        ocr = _paddle_ocr(language_hint)
        try:
            raw = ocr.ocr(str(image_path), cls=True)
        except TypeError:
            raw = ocr.ocr(str(image_path))
        image_width, image_height = _image_dimensions(image_path)
        lines, confidences, boxes = _flatten_paddle_result(
            raw,
            image_width=image_width,
            image_height=image_height,
        )
        result = OcrPageResult(
            text="\n".join(lines).strip(),
            engine="paddleocr",
            engine_version=_package_version("paddleocr"),
            language_hint=language_hint,
            confidence=_mean_confidence(confidences),
            page_number=page_number,
            duration_ms=_duration_ms(started),
            boxes=tuple(boxes),
        )
        if _better_ocr_result(result, best_result):
            best_result = result
        if language_hint != "en":
            break

    if best_result is None:
        raise OcrUnavailableError("paddleocr_no_result")
    return best_result


@lru_cache(maxsize=8)
def _paddle_ocr(language_hint: str):
    _ensure_paddlex_cache_home()
    try:
        from paddleocr import PaddleOCR
    except Exception as exc:
        raise OcrUnavailableError("paddleocr_unavailable") from exc

    try:
        return PaddleOCR(**_paddle_ocr_kwargs(language_hint))
    except TypeError:
        try:
            return PaddleOCR(lang=language_hint, use_angle_cls=True)
        except TypeError:
            return PaddleOCR(lang=language_hint)
    except Exception:
        if not _paddle_orientation_enabled():
            raise
        return PaddleOCR(**_paddle_ocr_kwargs(language_hint, orientation=False))


def _ensure_paddlex_cache_home() -> None:
    if os.environ.get("PADDLE_PDX_CACHE_HOME"):
        return
    cache_dir = Path(os.environ.get("ORDERFLOW_OCR_CACHE_DIR", ".paddlex-cache")).resolve()
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        return
    os.environ["PADDLE_PDX_CACHE_HOME"] = str(cache_dir)


def _paddle_orientation_enabled() -> bool:
    return os.environ.get("ORDERFLOW_OCR_PADDLE_ORIENTATION", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _paddle_ocr_kwargs(language_hint: str, *, orientation: bool | None = None) -> dict[str, Any]:
    use_orientation = _paddle_orientation_enabled() if orientation is None else orientation
    return {
        "enable_mkldnn": False,
        "text_detection_model_name": _paddle_text_detection_model_name(),
        "text_recognition_model_name": _paddle_text_recognition_model_name(language_hint),
        "use_doc_orientation_classify": use_orientation,
        "use_doc_unwarping": False,
        "use_textline_orientation": use_orientation,
        "text_det_limit_side_len": _ocr_image_max_side(),
        "text_det_limit_type": "max",
    }


def _paddle_text_detection_model_name() -> str:
    return os.environ.get("ORDERFLOW_OCR_PADDLE_DET_MODEL", "PP-OCRv5_mobile_det").strip()


def _paddle_text_recognition_model_name(language_hint: str) -> str:
    override = os.environ.get("ORDERFLOW_OCR_PADDLE_REC_MODEL", "").strip()
    if override:
        return override
    language = language_hint.strip().lower()
    if language == "en":
        return "en_PP-OCRv5_mobile_rec"
    if language in {"hi", "mr", "ne", "sa"}:
        return "devanagari_PP-OCRv5_mobile_rec"
    if language == "ta":
        return "ta_PP-OCRv5_mobile_rec"
    if language == "te":
        return "te_PP-OCRv5_mobile_rec"
    if language == "ka":
        return "ka_PP-OCRv3_mobile_rec"
    return "en_PP-OCRv5_mobile_rec"


def _flatten_paddle_result(
    raw: object,
    *,
    image_width: float | None = None,
    image_height: float | None = None,
) -> tuple[list[str], list[float], list[dict[str, Any]]]:
    lines: list[str] = []
    confidences: list[float] = []
    boxes: list[dict[str, Any]] = []

    def visit(value: object) -> None:
        if isinstance(value, dict):
            result_value = value.get("res") if isinstance(value.get("res"), dict) else value
            rec_texts = result_value.get("rec_texts")
            rec_scores = result_value.get("rec_scores")
            rec_boxes = result_value.get("rec_boxes")
            rec_polys = result_value.get("rec_polys")
            if rec_polys is None:
                rec_polys = result_value.get("dt_polys")
            if isinstance(rec_texts, list):
                for idx, text in enumerate(rec_texts):
                    if isinstance(text, str) and text.strip():
                        cleaned = text.strip()
                        lines.append(cleaned)
                        confidence = _sequence_number(rec_scores, idx)
                        box = _box_from_paddle_sequences(
                            rec_boxes=rec_boxes,
                            rec_polys=rec_polys,
                            index=idx,
                            image_width=image_width,
                            image_height=image_height,
                        )
                        if box is not None:
                            boxes.append(
                                {
                                    "text": cleaned,
                                    "bbox": box,
                                    "polygon": _polygon_from_sequence(
                                        rec_polys, idx, image_width, image_height
                                    ),
                                    "confidence": confidence,
                                    "granularity": "line",
                                    "source": "ocr",
                                }
                            )
            if isinstance(rec_scores, list):
                for confidence in rec_scores:
                    if isinstance(confidence, (int, float)) and not isinstance(confidence, bool):
                        confidences.append(float(confidence))
            return
        if isinstance(value, str):
            if value.strip():
                lines.append(value.strip())
            return
        if not isinstance(value, (list, tuple)):
            return
        if len(value) >= 2 and isinstance(value[1], (list, tuple)) and value[1]:
            candidate_box = value[0] if value else None
            text = value[1][0]
            confidence = value[1][1] if len(value[1]) > 1 else None
            if isinstance(text, str) and text.strip():
                cleaned = text.strip()
                lines.append(cleaned)
                box = _bbox_from_polygon(candidate_box, image_width, image_height)
                if box is not None:
                    boxes.append(
                        {
                            "text": cleaned,
                            "bbox": box,
                            "polygon": _normalize_polygon(candidate_box, image_width, image_height),
                            "confidence": (
                                float(confidence) if isinstance(confidence, (int, float)) else None
                            ),
                            "granularity": "line",
                            "source": "ocr",
                        }
                    )
            if isinstance(confidence, (int, float)) and not isinstance(confidence, bool):
                confidences.append(float(confidence))
            return
        for item in value:
            visit(item)

    visit(raw)
    return lines, confidences, boxes


def _image_dimensions(image_path: Path) -> tuple[float | None, float | None]:
    try:
        from PIL import Image
    except Exception:
        return None, None
    try:
        with Image.open(image_path) as image:
            width, height = image.size
    except Exception:
        return None, None
    return float(width), float(height)


def _sequence_number(value: object, index: int) -> float | None:
    try:
        item = value[index]  # type: ignore[index]
    except Exception:
        return None
    if isinstance(item, (int, float)) and not isinstance(item, bool):
        return float(item)
    return None


def _box_from_paddle_sequences(
    *,
    rec_boxes: object,
    rec_polys: object,
    index: int,
    image_width: float | None,
    image_height: float | None,
) -> dict[str, float] | None:
    try:
        box_value = rec_boxes[index]  # type: ignore[index]
    except Exception:
        box_value = None

    if box_value is not None:
        values = _numeric_sequence(box_value)
        if len(values) >= 4 and image_width and image_height:
            left, top, right, bottom = values[:4]
            return _normalize_rect(
                left,
                top,
                max(0.0, right - left),
                max(0.0, bottom - top),
                image_width,
                image_height,
            )

    try:
        poly_value = rec_polys[index]  # type: ignore[index]
    except Exception:
        poly_value = None
    return _bbox_from_polygon(poly_value, image_width, image_height)


def _bbox_from_polygon(
    value: object,
    image_width: float | None,
    image_height: float | None,
) -> dict[str, float] | None:
    polygon = _normalize_polygon(value, image_width, image_height)
    if not polygon:
        return None
    xs = [point["x"] for point in polygon]
    ys = [point["y"] for point in polygon]
    left = min(xs)
    top = min(ys)
    right = max(xs)
    bottom = max(ys)
    return {
        "left": round(left, 6),
        "top": round(top, 6),
        "width": round(max(0.0, right - left), 6),
        "height": round(max(0.0, bottom - top), 6),
    }


def _normalize_polygon(
    value: object,
    image_width: float | None,
    image_height: float | None,
) -> list[dict[str, float]] | None:
    if not image_width or not image_height:
        return None
    points: list[dict[str, float]] = []
    if not isinstance(value, (list, tuple)):
        return None
    for item in value:
        pair = _numeric_sequence(item)
        if len(pair) < 2:
            return None
        points.append(
            {
                "x": _fraction(pair[0], image_width),
                "y": _fraction(pair[1], image_height),
            }
        )
    return points or None


def _polygon_from_sequence(
    value: object,
    index: int,
    image_width: float | None,
    image_height: float | None,
) -> list[dict[str, float]] | None:
    try:
        item = value[index]  # type: ignore[index]
    except Exception:
        return None
    return _normalize_polygon(item, image_width, image_height)


def _numeric_sequence(value: object) -> list[float]:
    if not isinstance(value, (list, tuple)):
        tolist = getattr(value, "tolist", None)
        if callable(tolist):
            value = tolist()
    if not isinstance(value, (list, tuple)):
        return []
    result: list[float] = []
    for item in value:
        if isinstance(item, (list, tuple)):
            result.extend(_numeric_sequence(item))
        elif isinstance(item, (int, float)) and not isinstance(item, bool):
            result.append(float(item))
    return result


def _normalize_rect(
    left: float,
    top: float,
    width: float,
    height: float,
    image_width: float,
    image_height: float,
) -> dict[str, float]:
    return {
        "left": _fraction(left, image_width),
        "top": _fraction(top, image_height),
        "width": _fraction(width, image_width),
        "height": _fraction(height, image_height),
    }


def _fraction(value: float, total: float) -> float:
    if total <= 0:
        return 0.0
    return round(min(1.0, max(0.0, value / total)), 6)


def _run_tesseract(
    *,
    image_path: Path,
    page_number: int,
    source_language: str | None,
    settings: Any,
    started: float,
) -> OcrPageResult:
    executable = getattr(settings, "orderflow_ocr_tesseract_cmd", "tesseract") or "tesseract"
    language_hint = _tesseract_language(source_language)
    text_cmd = [executable, str(image_path), "stdout", "-l", language_hint, "--psm", "6"]
    completed = subprocess.run(
        text_cmd,
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    boxes, confidence = _tesseract_boxes_and_confidence(executable, image_path, language_hint)
    return OcrPageResult(
        text=completed.stdout.strip(),
        engine="tesseract",
        engine_version=_tesseract_version(executable),
        language_hint=language_hint,
        confidence=confidence,
        page_number=page_number,
        duration_ms=_duration_ms(started),
        boxes=tuple(boxes),
    )


def _tesseract_confidence(executable: str, image_path: Path, language_hint: str) -> float | None:
    _, confidence = _tesseract_boxes_and_confidence(executable, image_path, language_hint)
    return confidence


def _tesseract_boxes_and_confidence(
    executable: str,
    image_path: Path,
    language_hint: str,
) -> tuple[list[dict[str, Any]], float | None]:
    try:
        completed = subprocess.run(
            [executable, str(image_path), "stdout", "-l", language_hint, "--psm", "6", "tsv"],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except Exception:
        return [], None
    image_width, image_height = _image_dimensions(image_path)
    values: list[float] = []
    boxes: list[dict[str, Any]] = []
    for line in completed.stdout.splitlines()[1:]:
        parts = line.split("\t")
        if len(parts) < 11:
            continue
        try:
            confidence = float(parts[10])
        except ValueError:
            continue
        if confidence >= 0:
            normalized_confidence = confidence / 100.0
            values.append(normalized_confidence)
            text = parts[11].strip() if len(parts) > 11 else ""
            if text and image_width and image_height:
                try:
                    left = float(parts[6])
                    top = float(parts[7])
                    width = float(parts[8])
                    height = float(parts[9])
                except ValueError:
                    continue
                boxes.append(
                    {
                        "text": text,
                        "bbox": _normalize_rect(
                            left, top, width, height, image_width, image_height
                        ),
                        "polygon": None,
                        "confidence": normalized_confidence,
                        "granularity": "word",
                        "source": "ocr",
                    }
                )
    return boxes, _mean_confidence(values)


@lru_cache(maxsize=4)
def _tesseract_version(executable: str) -> str | None:
    try:
        completed = subprocess.run(
            [executable, "--version"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception:
        return None
    return completed.stdout.splitlines()[0].strip()[:120] if completed.stdout else None


def _engine_plan(settings: Any) -> list[str]:
    engines = [
        getattr(settings, "orderflow_ocr_primary_engine", "paddleocr"),
        getattr(settings, "orderflow_ocr_fallback_engine", "tesseract"),
    ]
    result: list[str] = []
    for engine in engines:
        normalized = str(engine or "").strip().lower()
        if normalized and normalized not in result:
            result.append(normalized)
    return result


def _ocr_result_is_usable(result: OcrPageResult, settings: Any) -> bool:
    text = result.text.strip()
    if not text:
        return False
    min_chars = max(1, int(getattr(settings, "orderflow_ocr_min_chars", 120) or 120))
    min_confidence = float(getattr(settings, "orderflow_ocr_min_confidence", 0.55) or 0.55)
    if len(text) < min_chars:
        return False
    if result.confidence is not None and result.confidence < min_confidence:
        return False
    if _script_match_score(text, result.language_hint) < _min_script_match_score(
        result.language_hint
    ):
        return False
    if _garbage_character_ratio(text) >= 0.18:
        return False
    return True


def _paddle_language(source_language: str | None) -> str:
    code = (source_language or "en").strip().lower()
    if code in {"hi", "mr", "ne", "sa", "ta", "te"}:
        return code
    if code == "kn":
        return "ka"
    return "en"


def _paddle_language_candidates(source_language: str | None) -> list[str]:
    raw_code = (source_language or "").strip().lower()
    primary = _paddle_language(source_language)
    if raw_code in {"hi", "mr", "ne", "sa", "ta", "te", "kn"}:
        return [primary]
    if raw_code in {"", "auto", "en"}:
        return ["en", "mr", "hi"]
    return [primary]


def _better_ocr_result(candidate: OcrPageResult, current: OcrPageResult | None) -> bool:
    if current is None:
        return True
    candidate_score = _ocr_quality_score(candidate)
    current_score = _ocr_quality_score(current)
    return candidate_score > current_score


def _ocr_quality_score(result: OcrPageResult) -> tuple[float, float, float, float, float, float]:
    text = result.text.strip()
    line_count = max(1, len([line for line in text.splitlines() if line.strip()]))
    return (
        _readability_score(text, result.language_hint),
        _script_match_score(text, result.language_hint),
        result.confidence or 0.0,
        min(1.0, len(text) / 2000),
        min(1.0, line_count / 25),
        -_garbage_character_ratio(text),
    )


def _readability_score(text: str, language_hint: str | None) -> float:
    if not text:
        return 0.0
    language = (language_hint or "en").split("+", 1)[0].strip().lower()
    garbage_penalty = 1.0 - min(1.0, _garbage_character_ratio(text) * 4)
    if language in {"hi", "mr", "ne", "sa", "ta", "te", "ka"}:
        return round(_script_match_score(text, language) * garbage_penalty, 4)
    return round(_latin_readability_score(text) * garbage_penalty, 4)


def _latin_readability_score(text: str) -> float:
    tokens = [token.casefold() for token in re.findall(r"[A-Za-z]{2,}", text)]
    if len(tokens) < 3:
        return 0.0
    common_hits = sum(1 for token in tokens if token in _COMMON_ENGLISH_WORDS)
    vowel_tokens = sum(1 for token in tokens if any(char in "aeiou" for char in token))
    repeated_tokens = len(tokens) - len(set(tokens))
    common_score = min(1.0, common_hits / max(3, len(tokens) * 0.18))
    vowel_score = vowel_tokens / len(tokens)
    repetition_penalty = min(0.35, repeated_tokens / len(tokens))
    return max(0.0, (common_score * 0.65) + (vowel_score * 0.35) - repetition_penalty)


def _script_match_score(text: str, language_hint: str | None) -> float:
    letters = [char for char in text if char.isalpha()]
    if not letters:
        return 0.0
    language = (language_hint or "en").split("+", 1)[0].strip().lower()
    if language in {"hi", "mr", "ne", "sa"}:
        return _range_ratio(letters, 0x0900, 0x097F)
    if language == "ta":
        return _range_ratio(letters, 0x0B80, 0x0BFF)
    if language == "te":
        return _range_ratio(letters, 0x0C00, 0x0C7F)
    if language == "ka":
        return _range_ratio(letters, 0x0C80, 0x0CFF)
    return sum(1 for char in letters if char.isascii()) / len(letters)


def _min_script_match_score(language_hint: str | None) -> float:
    language = (language_hint or "en").split("+", 1)[0].strip().lower()
    if language in {"hi", "mr", "ne", "sa", "ta", "te", "ka"}:
        return 0.35
    return 0.0


def _range_ratio(characters: list[str], start: int, end: int) -> float:
    return sum(1 for char in characters if start <= ord(char) <= end) / len(characters)


def _garbage_character_ratio(text: str) -> float:
    if not text:
        return 1.0
    allowed_punctuation = set(".,;:!?()[]{}-/\\'\"&%#@+*=<>|")
    garbage = 0
    for char in text:
        if char.isalnum() or char.isspace() or char in allowed_punctuation:
            continue
        codepoint = ord(char)
        if 0x0900 <= codepoint <= 0x0D7F:
            continue
        garbage += 1
    return garbage / len(text)


def _tesseract_language(source_language: str | None) -> str:
    code = (source_language or "en").strip().lower()
    mapping = {
        "hi": "hin+eng",
        "mr": "mar+eng",
        "ta": "tam+eng",
        "te": "tel+eng",
        "kn": "kan+eng",
        "ml": "mal+eng",
        "bn": "ben+eng",
        "gu": "guj+eng",
        "pa": "pan+eng",
        "ur": "urd+eng",
    }
    return mapping.get(code, "eng")


def _ocr_dpi(settings: Any) -> int:
    value = getattr(settings, "orderflow_ocr_dpi", 300) or 300
    return min(450, max(150, int(value)))


def _package_version(package_name: str) -> str | None:
    try:
        return importlib.metadata.version(package_name)
    except Exception:
        return None


def _mean_confidence(values: list[float]) -> float | None:
    valid = [min(1.0, max(0.0, value)) for value in values if isinstance(value, (int, float))]
    if not valid:
        return None
    return round(float(statistics.mean(valid)), 4)


def _duration_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _failure(
    page_number: int,
    started: float,
    engine: str | None,
    source_language: str | None,
    error: str,
) -> OcrPageResult:
    return OcrPageResult(
        text="",
        engine=engine,
        engine_version=None,
        language_hint=source_language,
        confidence=None,
        page_number=page_number,
        duration_ms=_duration_ms(started),
        error=error,
    )
