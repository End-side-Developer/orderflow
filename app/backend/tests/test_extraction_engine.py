from datetime import date
import pytest
from uuid import uuid4

import orderflow_api.api.extraction_engine as extraction_engine


def test_decode_document_text_prefers_docling_for_pdf(monkeypatch) -> None:
    def fake_decode_pdf_with_docling(payload: bytes, source_file_name: str | None) -> str | None:
        assert source_file_name == "judgment.pdf"
        return "Docling extracted directive text"

    monkeypatch.setattr(
        extraction_engine,
        "_decode_pdf_with_docling",
        fake_decode_pdf_with_docling,
    )

    parsed = extraction_engine.decode_document_text(
        b"%PDF-1.7",
        "application/pdf",
        "judgment.pdf",
    )

    assert parsed == "Docling extracted directive text"


def test_decode_document_text_falls_back_for_pdf_without_docling(monkeypatch) -> None:
    monkeypatch.setattr(
        extraction_engine,
        "_decode_pdf_with_docling",
        lambda payload, source_file_name: None,
    )

    payload = (
        b"%PDF-1.7\n"
        b"1 0 obj\n"
        b"(The respondent shall submit compliance affidavit within 7 days.)\n"
        b"endobj\n"
    )

    parsed = extraction_engine.decode_document_text(
        payload,
        "application/pdf",
        "judgment.pdf",
    )

    assert "respondent shall submit compliance affidavit within 7 days" in parsed.lower()


def test_decode_document_text_extracts_marathi_pdf_payload(monkeypatch) -> None:
    monkeypatch.setattr(
        extraction_engine,
        "_decode_pdf_with_docling",
        lambda payload, source_file_name: None,
    )

    marathi_clause = (
        "प्रतिवादीने सात दिवसांच्या आत अनुपालन प्रतिज्ञापत्र दाखल करावे "
        "आणि न्यायालयात सादर करावे."
    )
    payload = (
        b"%PDF-1.7\n"
        b"1 0 obj\n("
        + marathi_clause.encode("utf-8")
        + b")\nendobj\n"
    )

    parsed = extraction_engine.decode_document_text(
        payload,
        "application/pdf",
        "judgment-marathi.pdf",
    )

    assert "प्रतिवादी" in parsed
    assert "अनुपालन" in parsed


def test_decode_document_text_rejects_pdf_structure_noise(monkeypatch) -> None:
    """Binary fallback must not treat PDF dictionary tokens as document text.

    Reproduces the case where docling is missing, pypdf cannot decode the
    fonts, and the binary fallback would otherwise scrape `%PDF-1.7`,
    `<< /Filter /FlateDecode /Length ... >>`, `obj`, `endobj`, etc. and
    surface them as the document body.
    """
    monkeypatch.setattr(
        extraction_engine,
        "_decode_pdf_with_docling",
        lambda payload, source_file_name: None,
    )
    monkeypatch.setattr(
        extraction_engine,
        "_decode_pdf_with_pypdf",
        lambda payload: None,
    )

    payload = (
        b"%PDF-1.7\n"
        b"4 0 obj\n"
        b"<< /Filter /FlateDecode /Length 30218 >>\n"
        b"stream\n"
        b"(garbled binary stream content here that should never reach the user)\n"
        b"endstream\n"
        b"endobj\n"
        b"xref\n"
        b"trailer << /Size 5 >>\n"
        b"startxref\n"
    )

    with pytest.raises(ValueError, match="Unable to extract text from PDF"):
        extraction_engine.decode_document_text(
            payload,
            "application/pdf",
            "judgment.pdf",
        )


def test_decode_document_text_rejects_pypdf_replacement_char_mojibake(monkeypatch) -> None:
    """When pypdf returns mostly U+FFFD it means font decoding failed.

    The extractor must reject this rather than passing meaningless
    replacement-character soup to the AI summarizer.
    """
    monkeypatch.setattr(
        extraction_engine,
        "_decode_pdf_with_docling",
        lambda payload, source_file_name: None,
    )

    class _FakePage:
        def __init__(self, text: str) -> None:
            self._text = text

        def extract_text(self) -> str:
            return self._text

    class _FakeReader:
        def __init__(self, *_args, **_kwargs) -> None:
            self.pages = [_FakePage("� � � � � � � � � � � � � � � � � � � �")]

    import pypdf as _pypdf_module

    monkeypatch.setattr(_pypdf_module, "PdfReader", _FakeReader)

    payload = b"%PDF-1.7\n%bogus\n"

    with pytest.raises(ValueError, match="Unable to extract text from PDF"):
        extraction_engine.decode_document_text(
            payload,
            "application/pdf",
            "judgment.pdf",
        )


def test_looks_like_natural_language_accepts_devanagari() -> None:
    marathi_text = (
        "प्रतिवादीने सात दिवसांच्या आत अनुपालन प्रतिज्ञापत्र दाखल करावे."
    )
    assert extraction_engine._looks_like_natural_language(marathi_text) is True


def test_decode_document_text_raises_when_pdf_has_no_extractable_text(monkeypatch) -> None:
    monkeypatch.setattr(
        extraction_engine,
        "_decode_pdf_with_docling",
        lambda payload, source_file_name: None,
    )

    with pytest.raises(ValueError, match="Unable to extract text from PDF"):
        extraction_engine.decode_document_text(
            bytes([0, 159, 255, 0, 17, 3, 2, 0, 0, 1, 2, 3, 4, 5, 6]),
            "application/pdf",
            "judgment.pdf",
        )


def test_decode_document_text_strips_nul_bytes_for_text_payload() -> None:
    parsed = extraction_engine.decode_document_text(
        b"The respondent shall submit\x00 compliance affidavit within 7 days.",
        "text/plain",
        "judgment.txt",
    )

    assert "\x00" not in parsed
    assert "respondent shall submit" in parsed.lower()


def test_decode_document_text_rejects_binary_like_pdf_payload(monkeypatch) -> None:
    monkeypatch.setattr(
        extraction_engine,
        "_decode_pdf_with_docling",
        lambda payload, source_file_name: None,
    )

    payload = (
        b"%PDF-1.7\x00\x00\x10\x8f\x91\x00"
        b"\x03\x04\x00\x10\x00\x12\x00\x88\x99\x00\x00"
        b"https://www.bailii.org/ew/cases/EWHC/Ch/2006/1770.html\x00"
        b"\x80\x00\x00\x01\xff\x00\x08\x00\x90\x00\x00\x00\x00"
    )

    with pytest.raises(ValueError, match="Unable to extract text from PDF"):
        extraction_engine.decode_document_text(
            payload,
            "application/pdf",
            "judgment.pdf",
        )


def test_decode_document_text_rejects_symbol_heavy_pdf_gibberish(monkeypatch) -> None:
    monkeypatch.setattr(
        extraction_engine,
        "_decode_pdf_with_docling",
        lambda payload, source_file_name: None,
    )

    payload = (
        b"%PDF-1.7\n"
        b"1 0 obj\n"
        b"(4N%hjjJ uozjg0:oF7{,vy&qBF4y;C^gT3_MVa tK0UAsx&RhMNlrNx wuU #6LSnhUV;T4X1NBIO1Pe5D)\n"
        b"endobj\n"
    )

    with pytest.raises(ValueError, match="Unable to extract text from PDF"):
        extraction_engine.decode_document_text(
            payload,
            "application/pdf",
            "judgment.pdf",
        )


def test_segment_clauses_tracks_page_number_and_offsets() -> None:
    document_id = uuid4()
    raw_text = (
        "The respondent shall submit a compliance affidavit within 7 days.\n"
        "The registry will issue notice.\f"
        "The district authority must file status report in 10 days."
    )

    clauses = extraction_engine.segment_clauses(raw_text=raw_text, document_id=document_id)

    assert len(clauses) >= 3
    first = clauses[0]
    last = clauses[-1]

    assert first.page_number == 1
    assert first.span_start == 0
    assert first.span_end is not None
    assert last.page_number == 2
    assert last.span_start is not None
    assert last.span_end is not None
    assert last.span_start < last.span_end


def test_extract_obligations_emits_rich_clause_span_tokens() -> None:
    document_id = uuid4()
    raw_text = "Petitioner shall file reply within 3 days."

    clauses = extraction_engine.segment_clauses(raw_text=raw_text, document_id=document_id)
    obligations = extraction_engine.extract_obligations(clauses=clauses, document_id=document_id)

    assert len(obligations) == 1
    citation_span = obligations[0].citation_clause_span
    assert citation_span.startswith("p1:c1:")
    assert "-" in citation_span
    assert obligations[0].metadata["extractor_version"] == "structured-v1"


def test_extract_obligations_builds_structured_fields_and_confidence_annotations() -> None:
    document_id = uuid4()
    raw_text = "District Administration shall submit compliance affidavit by 25/12/2099."

    clauses = extraction_engine.segment_clauses(raw_text=raw_text, document_id=document_id)
    obligations = extraction_engine.extract_obligations(clauses=clauses, document_id=document_id)

    assert len(obligations) == 1
    obligation = obligations[0]
    annotations = obligation.metadata["confidence_annotations"]
    structured_fields = obligation.metadata["structured_fields"]

    assert obligation.owner_hint == "District Administration"
    assert obligation.due_date == date(2099, 12, 25)
    assert structured_fields["action_phrase"].startswith("submit compliance affidavit")
    assert structured_fields["deadline_source"] == "explicit_date"
    assert annotations["extractor_version"] == "structured-v1"
    assert annotations["components"]["directive_signal"] >= 0.9
    assert annotations["components"]["owner_signal"] >= 0.9
