import pytest

from orderflow_api.api import indian_ecourts_lookup


def test_resolve_source_url_prefers_local_sample_map(monkeypatch: pytest.MonkeyPatch) -> None:
    expected_url = (
        "https://delhihighcourt.nic.in/app/showFileJudgment/75005022026CW85242025_154137.pdf"
    )

    monkeypatch.setattr(
        indian_ecourts_lookup,
        "_resolve_case_id_from_local_samples",
        lambda _identifier: expected_url,
    )

    def _should_not_call_latest_feed() -> list[str]:
        raise AssertionError("latest judgments feed should not be called for known local samples")

    monkeypatch.setattr(
        indian_ecourts_lookup,
        "_fetch_latest_judgment_links",
        _should_not_call_latest_feed,
    )

    resolved = indian_ecourts_lookup._resolve_source_url("W.P.(C) 8524/2025")

    assert resolved == expected_url


def test_resolve_source_url_ignores_latest_feed_errors_when_no_sample(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        indian_ecourts_lookup,
        "_resolve_case_id_from_local_samples",
        lambda _identifier: None,
    )

    def _failing_latest_feed() -> list[str]:
        raise RuntimeError("upstream latest feed unavailable")

    monkeypatch.setattr(
        indian_ecourts_lookup,
        "_fetch_latest_judgment_links",
        _failing_latest_feed,
    )

    with pytest.raises(ValueError, match="was understood but no matching judgment was found"):
        indian_ecourts_lookup._resolve_source_url("W.P.(C) 9999/2025")


def test_resolve_source_url_accepts_services_ecourts_direct_pdf_url() -> None:
    url = "https://services.ecourts.gov.in/orders/demo-order-copy.pdf?download=1"

    resolved = indian_ecourts_lookup._resolve_source_url(url)

    assert resolved == url


def test_resolve_source_url_rejects_services_ecourts_non_pdf_url() -> None:
    url = "https://services.ecourts.gov.in/ecourtindia_v6/?p=courtorder/index"

    with pytest.raises(ValueError, match="captcha-protected"):
        indian_ecourts_lookup._resolve_source_url(url)
