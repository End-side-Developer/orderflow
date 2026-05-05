from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace
from uuid import uuid4

import pytest
from temporalio import exceptions as temporal_exceptions

from orderflow_worker.activities import intake
from orderflow_worker import main as worker_main
from orderflow_worker.workflows import intake as intake_workflow


class Record(SimpleNamespace):
    def model_dump(self, mode: str = "json") -> dict[str, object]:
        return {
            key: str(value) if key in {"id", "document_id"} else value
            for key, value in self.__dict__.items()
        }


def test_worker_activity_imports() -> None:
    assert callable(intake.activity_extract_page_cached)
    assert callable(intake.activity_list_completed_pages)
    assert callable(intake.activity_generate_full_summary)
    assert callable(intake.activity_extract_action_plan)
    assert callable(intake.activity_mark_intake_stage)
    assert callable(intake.activity_pause_intake_job)
    assert callable(intake.activity_resume_intake_job)
    assert callable(worker_main.run_worker)


def test_intake_workflow_payload_helpers_keep_gates_explicit() -> None:
    payload = {
        "document_id": str(uuid4()),
        "total_pages": "3",
        "page_2_content_hash": "hash-two",
    }

    page_numbers = intake_workflow._page_numbers_from_payload(payload)
    page_context = intake_workflow._page_extraction_context(
        payload,
        page_number=2,
        total_pages=max(page_numbers),
    )
    completed_context = intake_workflow._completed_pages_context(
        payload,
        page_numbers=page_numbers,
    )
    completed_by_number = intake_workflow._completed_pages_by_number(
        {
            "completed_pages": [
                {"page_number": 2, "cache_status": "skipped_completed"},
                {"page_number": 0, "cache_status": "ignored"},
            ]
        }
    )

    assert page_numbers == [1, 2, 3]
    assert page_context["page_number"] == "2"
    assert page_context["total_pages"] == "3"
    assert page_context["content_hash"] == "hash-two"
    assert page_context["prompt_version"] == (intake.DEFAULT_PAGE_EXTRACTION_PROMPT_VERSION)
    assert completed_context["content_hash_2"] == "hash-two"
    assert completed_context["page_numbers"] == "1,2,3"
    assert completed_context["ai_model"] == (intake.DEFAULT_PAGE_EXTRACTION_MODEL)
    assert completed_by_number == {2: {"page_number": 2, "cache_status": "skipped_completed"}}
    assert not intake_workflow._payload_bool(payload, "auto_advance_summary")
    assert not intake_workflow._payload_bool(
        payload,
        "auto_advance_action_plan",
    )
    assert not intake_workflow._payload_bool(payload, "auto_finalize_review")


def test_resolve_page_concurrency_clamps_to_worker_settings(
    monkeypatch,
) -> None:
    payload = {"current_concurrency": "9"}
    monkeypatch.setattr(
        intake_workflow,
        "settings",
        SimpleNamespace(
            orderflow_intake_min_concurrency=2,
            orderflow_intake_max_concurrency=3,
        ),
    )

    current, maximum = intake_workflow._resolve_page_concurrency(payload)

    assert current == 3
    assert maximum == 3


def test_restore_concurrency_after_success_streak() -> None:
    current, streak, updated = intake_workflow._maybe_restore_concurrency(
        4,
        1,
        4,
    )
    assert (current, streak, updated) == (1, 4, False)

    current, streak, updated = intake_workflow._maybe_restore_concurrency(
        5,
        1,
        4,
    )
    assert (current, streak, updated) == (2, 0, True)

    current, streak, updated = intake_workflow._maybe_restore_concurrency(
        5,
        3,
        4,
    )
    assert (current, streak, updated) == (4, 0, True)

    current, streak, updated = intake_workflow._maybe_restore_concurrency(
        5,
        4,
        4,
    )
    assert (current, streak, updated) == (4, 5, False)


def test_resume_pages_to_extract_skips_completed() -> None:
    page_numbers = [1, 2, 3, 4, 5, 6]
    completed_pages = {1: {"page_number": 1}, 3: {"page_number": 3}}

    remaining = intake_workflow._pages_to_extract(
        page_numbers,
        completed_pages,
    )

    assert remaining == [2, 4, 5, 6]


def test_rate_limit_backoff_plan_halves_and_buffers() -> None:
    new_concurrency, pause_seconds = intake_workflow._rate_limit_backoff_plan(
        4,
        12,
    )

    assert new_concurrency == 2
    assert pause_seconds == 12 + intake_workflow.RATE_LIMIT_BUFFER_SECONDS


def test_adaptive_concurrency_quota_error_halves_pauses_and_restores() -> None:
    error = temporal_exceptions.ApplicationError(
        "Rate limit encountered",
        {
            "retry_after_seconds": 12,
            "error_code": "ai_rate_limit_rpm",
            "error_message": "AI RPM limit reached.",
        },
        type="rate_limit",
        non_retryable=True,
    )

    details = intake_workflow._rate_limit_details(error)

    assert details == intake_workflow.RateLimitDetails(
        retry_after_seconds=12,
        error_code="ai_rate_limit_rpm",
        error_message="AI RPM limit reached.",
    )
    current_concurrency, pause_seconds = intake_workflow._rate_limit_backoff_plan(
        4,
        details.retry_after_seconds,
    )
    retry_trace = intake_workflow._workflow_trace_attributes(
        document_id=str(uuid4()),
        workflow_stage="pages_extracting",
        page_number=3,
        retry_state="paused",
        retry_after_seconds=details.retry_after_seconds,
        current_concurrency=current_concurrency,
    )

    assert current_concurrency == 2
    assert pause_seconds == 12 + intake_workflow.RATE_LIMIT_BUFFER_SECONDS
    assert retry_trace["orderflow.retry.state"] == "paused"
    assert retry_trace["orderflow.retry.after_seconds"] == 12
    assert retry_trace["orderflow.concurrency.current"] == 2

    success_streak = 0
    restored = False
    for _ in range(intake_workflow.RECOVERY_SUCCESS_TARGET):
        success_streak += 1
        current_concurrency, success_streak, restored = (
            intake_workflow._maybe_restore_concurrency(
                success_streak,
                current_concurrency,
                maximum=4,
            )
        )

    assert (current_concurrency, success_streak, restored) == (4, 0, True)


def test_worker_trace_attributes_cover_page_cache_and_retry_state() -> None:
    document_id = str(uuid4())
    context = SimpleNamespace(
        document_id=document_id,
        page_number=2,
        content_hash="hash-two",
        prompt_version=intake.DEFAULT_PAGE_EXTRACTION_PROMPT_VERSION,
        source_language="en",
        translation_status="not_required",
        translation_required=False,
    )
    summary = Record(
        id=uuid4(),
        document_id=document_id,
        page_number=2,
        summary="Short summary",
        confidence=0.91,
        ai_model=intake.DEFAULT_PAGE_EXTRACTION_MODEL,
        ai_provider=intake.DEFAULT_PAGE_EXTRACTION_PROVIDER,
    )
    progress = Record(stage="pages_extracting")

    result = intake._page_extraction_result(
        context=context,
        cache_status="hit",
        summary_record=summary,
        job_progress=progress,
    )
    retry_trace = intake._trace_attributes(
        document_id=document_id,
        workflow_stage="pages_extracting",
        page_number=2,
        retry_state="paused",
        retry_after_seconds=30,
        current_concurrency=1,
    )

    assert result["trace"] == {
        "orderflow.document_id": document_id,
        "orderflow.workflow.stage": "pages_extracting",
        "orderflow.page_number": 2,
        "orderflow.cache.status": "hit",
    }
    assert "summary" not in result["trace"]
    assert retry_trace["orderflow.retry.state"] == "paused"
    assert retry_trace["orderflow.retry.after_seconds"] == 30
    assert retry_trace["orderflow.concurrency.current"] == 1


def test_workflow_result_includes_safe_trace_attributes() -> None:
    document_id = str(uuid4())
    retry_trace = intake_workflow._workflow_trace_attributes(
        document_id=document_id,
        workflow_stage="pages_extracting",
        page_number=4,
        retry_state="paused",
        retry_after_seconds=20,
        current_concurrency=1,
    )

    result = intake_workflow._workflow_result(
        document_id=document_id,
        state="finalized",
        stages=[],
        page_results=[],
        awaiting="complete",
        retry_traces=[retry_trace],
    )

    assert result["trace"] == {
        "orderflow.document_id": document_id,
        "orderflow.workflow.stage": "finalized",
    }
    assert result["retry_traces"] == [retry_trace]


def test_full_summary_uses_cached_page_summaries(monkeypatch) -> None:
    document_id = uuid4()

    class Backend:
        def __init__(self) -> None:
            self.page_summaries = [
                Record(
                    id=uuid4(),
                    page_number=1,
                    summary="Cached page summary",
                    key_points=["Key point"],
                    extracted_places=[],
                    confidence=0.91,
                )
            ]
            self.obligations = [
                Record(
                    id=uuid4(),
                    title="Issue appointment order",
                    description="Issue order within 30 days.",
                    confidence=0.86,
                    owner_hint="Education Department",
                    citation=SimpleNamespace(page_number=1),
                )
            ]
            self.upserts: list[dict[str, object]] = []
            self.stage_updates: list[str] = []

        def get_document_summary(self, *args, **kwargs):  # noqa: ANN001, ANN003
            return None

        def get_extraction_job(self, *args, **kwargs):  # noqa: ANN001, ANN003
            return Record(stage="summary_pending")

        def list_page_summaries(self, *args, **kwargs):  # noqa: ANN001, ANN003
            return list(self.page_summaries)

        def list_persisted_obligations(self, *args, **kwargs):  # noqa: ANN001, ANN003
            return list(self.obligations)

        def update_extraction_job_stage(self, *args, **kwargs):  # noqa: ANN001, ANN003
            stage = kwargs.get("stage") or (args[1] if len(args) > 1 else None)
            self.stage_updates.append(str(stage))
            return Record(stage=stage)

        def upsert_document_summary(self, **kwargs):  # noqa: ANN003
            self.upserts.append(kwargs)
            return Record(id=uuid4(), **kwargs)

    backend = Backend()
    monkeypatch.setattr(
        intake,
        "_load_document_summary_backend",
        lambda: backend,
    )

    result = asyncio.run(intake.activity_generate_full_summary({"document_id": str(document_id)}))

    assert result["cache_status"] == "miss_generated"
    assert "1 cached page summary record(s)" in result["overview"]
    assert backend.upserts


def test_full_summary_cache_hit_skips_provider_calls(monkeypatch) -> None:
    document_id = uuid4()

    class Backend:
        def __init__(self) -> None:
            self.stage_updates: list[str] = []

        def get_document_summary(self, *args, **kwargs):  # noqa: ANN001, ANN003
            return Record(
                id=uuid4(),
                overview="Cached summary",
                confidence=0.94,
                ai_model=intake.DEFAULT_DOCUMENT_SUMMARY_MODEL,
                ai_provider=intake.DEFAULT_DOCUMENT_SUMMARY_PROVIDER,
            )

        def get_extraction_job(self, *args, **kwargs):  # noqa: ANN001, ANN003
            return Record(stage="summary_pending")

        def update_extraction_job_stage(self, *args, **kwargs):  # noqa: ANN001, ANN003
            stage = kwargs.get("stage") or (args[1] if len(args) > 1 else None)
            self.stage_updates.append(str(stage))
            return Record(stage=stage)

        def list_page_summaries(self, *args, **kwargs):  # noqa: ANN001, ANN003
            raise AssertionError("Unexpected page summary lookup on cache hit")

        def list_persisted_obligations(self, *args, **kwargs):  # noqa: ANN001, ANN003
            raise AssertionError("Unexpected obligations lookup on cache hit")

        def upsert_document_summary(self, **kwargs):  # noqa: ANN003
            raise AssertionError("Unexpected summary upsert on cache hit")

    backend = Backend()
    monkeypatch.setattr(
        intake,
        "_load_document_summary_backend",
        lambda: backend,
    )

    result = asyncio.run(intake.activity_generate_full_summary({"document_id": str(document_id)}))

    assert result["cache_status"] == "hit"
    assert result["overview"] == "Cached summary"
    assert result["job_stage"] == "summary_done"
    assert backend.stage_updates == ["summary_done"]


def test_case_basics_extracts_core_fields() -> None:
    page_text = """
IN THE HIGH COURT OF DELHI AT NEW DELHI
W.P.(C) No. 1234/2024
ABC Petitioner
VERSUS
Govt of NCT of Delhi Respondent
Date of Order: 05/02/2026
CORAM: HON'BLE MR. JUSTICE XYZ
"""
    page_summary = Record(
        page_number=1,
        page_text=page_text,
        summary="Summary text",
        key_points=["Service dispute"],
    )
    obligations = [
        Record(
            owner_hint="Education Department",
            confidence=0.8,
            citation=SimpleNamespace(page_number=1),
        )
    ]

    basics = intake._extract_case_basics([page_summary], obligations)

    assert basics["case_number"] == "W.P.(C) No. 1234/2024"
    assert basics["court_name"] == "HIGH COURT OF DELHI AT NEW DELHI"
    assert basics["case_type"] == "Writ Petition"
    assert basics["order_date"] == "05/02/2026"
    assert basics["petitioner"] == "ABC"
    assert basics["respondent"] == "Govt of NCT of Delhi"
    assert basics["judge_name"] == "HON'BLE MR. JUSTICE XYZ"
    assert basics["department_involved"] == "Education Department"


def test_document_overview_includes_simple_narrative() -> None:
    case_basics = {
        "case_number": "W.P.(C) No. 1234/2024",
        "court_name": "HIGH COURT OF DELHI AT NEW DELHI",
        "case_type": "Writ Petition",
        "order_date": "05/02/2026",
        "petitioner": "ABC",
        "respondent": "Govt of NCT of Delhi",
    }
    page_summaries = [
        Record(
            summary="The petitioner challenged the refusal of appointment.",
            key_points=["Appointment refused"],
        )
    ]
    obligations = [
        Record(title="Issue appointment order"),
        Record(title="Submit compliance report"),
    ]

    overview = intake._build_document_overview(
        page_summaries,
        obligations,
        case_basics,
    )

    assert "This judgment concerns Writ Petition" in overview
    assert "HIGH COURT OF DELHI" in overview
    assert "petitioner ABC" in overview
    assert "order date recorded is 05/02/2026" in overview


def test_key_directives_include_flags_and_references() -> None:
    obligations = [
        Record(
            title="Submit compliance report",
            description="The department shall submit a report.",
            confidence=0.92,
            citation=SimpleNamespace(page_number=2, clause_span="para 12"),
        ),
        Record(
            title="Consider representation",
            description="The authority may consider the representation.",
            confidence=0.61,
            citation=SimpleNamespace(page_number=4, clause_index=3),
        ),
    ]

    directives = intake._build_key_directives(obligations)

    assert directives[0]["directive_kind"] == "mandatory"
    assert directives[0]["compliance_required"] == "yes"
    assert directives[0]["source_paragraph_reference"] == "para 12"
    assert directives[1]["directive_kind"] == "advisory"
    assert directives[1]["compliance_required"] == "needs_review"
    assert directives[1]["source_paragraph_reference"] == "Clause 3"


def test_important_dates_marks_inferred_and_page_dates() -> None:
    obligations = [
        Record(
            title="Submit report",
            due_date="2026-05-20",
            deadline_source="inferred",
            confidence=0.7,
            citation=SimpleNamespace(page_number=2),
        )
    ]
    page_summaries = [
        Record(
            page_number=1,
            page_text="Hearing on 12/06/2026 and order on 15/06/2026.",
            confidence=0.9,
        )
    ]

    dates = intake._build_important_dates(obligations, page_summaries)

    assert dates[0]["is_inferred"] is True
    assert any(item["date_text"] == "12/06/2026" for item in dates)


def test_entities_and_departments_include_source_evidence() -> None:
    obligations = [
        Record(
            title="Issue appointment order",
            owner_hint="Education Department",
            confidence=0.76,
            citation=SimpleNamespace(page_number=5),
        )
    ]

    entities = intake._build_entities(obligations)
    departments = intake._build_responsible_departments(obligations)

    assert entities[0]["metadata"]["source_evidence"]
    assert departments[0]["source_evidence"]


def test_flow_graph_includes_party_and_next_edges() -> None:
    case_basics = {
        "petitioner": "ABC",
        "respondent": "State of Delhi",
    }
    page_summaries = [
        Record(page_number=1, summary="Intro page"),
        Record(page_number=2, summary="Order is directed"),
    ]
    obligations = [
        Record(
            title="Issue appointment order",
            description="Issue the order within 30 days.",
            citation=SimpleNamespace(page_number=2),
        )
    ]

    graph = intake._build_flow_graph(
        intake.DocumentSummaryContext(
            document_id=str(uuid4()),
            document_uuid=uuid4(),
            prompt_version="v1",
            ai_provider="openai",
            ai_model="gpt-4o",
            bypass_cache=False,
        ),
        page_summaries,
        obligations,
        case_basics,
    )

    node_types = {node["node_type"] for node in graph["nodes"]}
    edge_relations = {edge["relation"] for edge in graph["edges"]}

    assert "party" in node_types
    assert "event" in node_types
    assert "next" in edge_relations


def test_map_data_rule_requires_geo_and_distinct_pages() -> None:
    page_summaries = [
        Record(
            page_number=1,
            extracted_places=[
                Record(
                    normalized_name="delhi",
                    name="Delhi",
                    district="Delhi",
                    lat=28.6,
                    lng=77.2,
                    source_page_number=1,
                ),
                Record(
                    normalized_name="gurugram",
                    name="Gurugram",
                    district="Gurugram",
                    lat=28.4,
                    lng=77.0,
                    source_page_number=1,
                ),
            ],
        ),
        Record(
            page_number=2,
            extracted_places=[
                Record(
                    normalized_name="noida",
                    name="Noida",
                    district="Gautam Budh Nagar",
                    lat=28.5,
                    lng=77.4,
                    source_page_number=2,
                )
            ],
        ),
    ]

    map_data = intake._build_map_data(page_summaries)

    assert map_data["available"] is True
    assert len(map_data["places"]) == 3


def test_map_data_rule_returns_reason_on_failure() -> None:
    page_summaries = [
        Record(
            page_number=1,
            extracted_places=[
                Record(
                    normalized_name="delhi",
                    name="Delhi",
                    district="Delhi",
                    lat=28.6,
                    lng=77.2,
                    source_page_number=1,
                )
            ],
        )
    ]

    map_data = intake._build_map_data(page_summaries)

    assert map_data["available"] is False
    assert map_data["places"] == []
    assert "Map flow not generated" in map_data["reason"]


def test_nature_of_action_classification_covers_required_categories() -> None:
    cases = [
        ("Pay arrears", "Pay salary arrears within 30 days.", "payment"),
        ("Appointment order", "Appoint the petitioner as teacher.", "appointment"),
        ("Submit representation", "Submit representation to the authority.", "submission"),
        ("Policy update", "Issue policy guideline for compliance.", "policy"),
        ("Reconsider claim", "Consider afresh the pending claim.", "reconsideration"),
        ("Personal hearing", "Schedule personal hearing for the petitioner.", "hearing"),
        ("Appeal review", "File appeal review petition within limitation.", "appeal_review"),
        ("Update record", "Update service record details.", "record_update"),
        ("General note", "No action required at this time.", "other"),
    ]

    for title, description, expected in cases:
        obligation = Record(title=title, description=description)
        assert intake._classify_nature_of_action(obligation) == expected


def test_page_activity_wraps_rate_limit_errors(monkeypatch) -> None:
    document_id = uuid4()

    class FakeRateLimitError(Exception):
        retry_after_seconds = 7
        code = "fake_rate_limit"

    async def fake_run(*_args, **_kwargs):  # noqa: ANN001, ANN003
        raise FakeRateLimitError("Rate limited")

    monkeypatch.setattr(intake, "_run_page_extraction_cached", fake_run)
    monkeypatch.setattr(intake, "_record_page_extraction_failure", lambda **_: None)
    monkeypatch.setattr(intake, "_load_page_extraction_backend", lambda: object())

    with pytest.raises(temporal_exceptions.ApplicationError) as excinfo:
        asyncio.run(
            intake.activity_extract_page_cached(
                {
                    "document_id": str(document_id),
                    "page_number": 1,
                    "total_pages": 1,
                }
            )
        )

    assert excinfo.value.type == "rate_limit"
    assert excinfo.value.details
    assert excinfo.value.details[0]["retry_after_seconds"] == 7
    assert excinfo.value.details[0]["error_code"] == "ai_rate_limit_rpm"
    assert excinfo.value.details[0]["error_category"] == "rpm_limit"
    assert "AI RPM limit reached" in excinfo.value.details[0]["error_message"]


def test_user_facing_page_error_messages_cover_required_categories() -> None:
    class FakeProviderError(Exception):
        def __init__(
            self,
            message: str,
            *,
            code: str | None = None,
            retry_after_seconds: int | None = None,
        ) -> None:
            super().__init__(message)
            self.code = code
            self.retry_after_seconds = retry_after_seconds

    cases = [
        (
            FakeProviderError("requests_per_minute quota exceeded", retry_after_seconds=7),
            {},
            "ai_rate_limit_rpm",
            "rpm_limit",
            "AI RPM limit reached",
        ),
        (
            FakeProviderError("tokens_per_minute quota exceeded", retry_after_seconds=7),
            {},
            "ai_rate_limit_tpm",
            "tpm_limit",
            "AI TPM limit reached",
        ),
        (
            FakeProviderError("provider timed out", code="gemini_timeout"),
            {},
            "ai_timeout",
            "timeout",
            "timed out",
        ),
        (
            FakeProviderError("DNS connection failed", code="gemini_network_error"),
            {},
            "ai_network_error",
            "network",
            "Network problem",
        ),
        (
            ValueError("Unable to extract text from PDF: no readable text layer found"),
            {},
            "ocr_required",
            "ocr_failure",
            "Run OCR",
        ),
        (
            FakeProviderError("invalid JSON from provider", code="gemini_invalid_json"),
            {},
            "ai_invalid_json",
            "invalid_ai_json",
            "not valid JSON",
        ),
        (
            RuntimeError("provider stopped unexpectedly"),
            {"pages_completed": 2, "pages_total": 4},
            "partial_page_failure",
            "partial_page_failure",
            "Page 3 failed after 2 of 4 pages were saved",
        ),
    ]

    for error, kwargs, expected_code, expected_category, expected_text in cases:
        result = intake._user_facing_page_error(
            error,
            page_number=3,
            **kwargs,
        )

        assert result.code == expected_code
        assert result.category == expected_category
        assert expected_text in result.message


def test_worker_source_excerpt_limit_stays_ui_sized() -> None:
    excerpt = intake._truncate_text("x" * 1200, intake.MAX_SOURCE_EXCERPT_CHARS)

    assert intake.MAX_SOURCE_EXCERPT_CHARS == 800
    assert len(excerpt) <= 800
    assert excerpt.endswith("...")


def test_summary_signal_toggles_workflow_gate() -> None:
    workflow = intake_workflow.IntakeWorkflow()

    assert not workflow._advance_to_summary

    asyncio.run(workflow.signal_advance_to_summary())

    assert workflow._advance_to_summary


def test_action_plan_signal_toggles_workflow_gate() -> None:
    workflow = intake_workflow.IntakeWorkflow()

    assert not workflow._advance_to_action_plan

    asyncio.run(workflow.signal_advance_to_action_plan())

    assert workflow._advance_to_action_plan


def test_finalize_signal_toggles_workflow_gate() -> None:
    workflow = intake_workflow.IntakeWorkflow()

    assert not workflow._finalize_review

    asyncio.run(workflow.signal_finalize())

    assert workflow._finalize_review


def test_mark_intake_stage_activity_updates_stage(monkeypatch) -> None:
    document_id = uuid4()

    class Backend:
        def __init__(self) -> None:
            self.stage_updates: list[tuple[object, str]] = []

        def update_extraction_job_stage(self, document_id, stage):
            self.stage_updates.append((document_id, stage))
            return Record(document_id=document_id, stage=stage)

    backend = Backend()
    monkeypatch.setattr(intake, "_load_stage_marker_backend", lambda: backend)

    result = asyncio.run(
        intake.activity_mark_intake_stage({"document_id": str(document_id), "stage": "pages_done"})
    )

    assert result["stage"] == "pages_done"
    assert backend.stage_updates == [(document_id, "pages_done")]


def test_completed_pages_activity_skips_valid_cached_pages(
    monkeypatch,
) -> None:
    document_id = uuid4()

    class Backend:
        def __init__(self) -> None:
            self.summaries = [
                Record(
                    id=uuid4(),
                    document_id=document_id,
                    page_number=1,
                    summary="Cached page one",
                    content_hash="hash-one",
                    prompt_version=(intake.DEFAULT_PAGE_EXTRACTION_PROMPT_VERSION),
                    ai_model=intake.DEFAULT_PAGE_EXTRACTION_MODEL,
                    ai_provider=intake.DEFAULT_PAGE_EXTRACTION_PROVIDER,
                    confidence=0.92,
                ),
                Record(
                    id=uuid4(),
                    document_id=document_id,
                    page_number=2,
                    summary="Wrong prompt page two",
                    content_hash="hash-two",
                    prompt_version="old_prompt",
                    ai_model=intake.DEFAULT_PAGE_EXTRACTION_MODEL,
                    ai_provider=intake.DEFAULT_PAGE_EXTRACTION_PROVIDER,
                    confidence=0.7,
                ),
            ]
            self.progress_calls: list[tuple[object, dict[str, object]]] = []

        def list_page_summaries(self, document_id):
            return list(self.summaries)

        def update_extraction_job_progress(self, document_id, **values):
            self.progress_calls.append((document_id, values))
            return Record(stage="pages_extracting", **values)

    backend = Backend()
    monkeypatch.setattr(
        intake,
        "_load_completed_pages_backend",
        lambda: backend,
    )

    result = asyncio.run(
        intake.activity_list_completed_pages(
            {
                "document_id": str(document_id),
                "total_pages": "3",
                "page_numbers": "1,2,3",
                "content_hash_1": "hash-one",
                "content_hash_2": "hash-two",
                "prompt_version": (intake.DEFAULT_PAGE_EXTRACTION_PROMPT_VERSION),
                "ai_model": intake.DEFAULT_PAGE_EXTRACTION_MODEL,
                "ai_provider": intake.DEFAULT_PAGE_EXTRACTION_PROVIDER,
            }
        )
    )

    assert result["completed_page_numbers"] == [1]
    assert result["skipped_count"] == 1
    assert result["completed_pages"][0]["cache_status"] == ("skipped_completed")
    assert result["completed_pages"][0]["summary"] == "Cached page one"
    assert backend.progress_calls == [
        (
            document_id,
            {
                "pages_total": 3,
                "pages_completed": 1,
                "current_page": 1,
                "current_page_excerpt": {
                    "cache_status": "skipped_completed",
                    "skipped_page_numbers": [1],
                },
            },
        )
    ]


def test_worker_restart_resumability_simulation_skips_completed_pages(
    monkeypatch,
) -> None:
    document_id = uuid4()

    class Backend:
        def __init__(self) -> None:
            self.summaries = [
                Record(
                    id=uuid4(),
                    document_id=document_id,
                    page_number=1,
                    summary="Completed page one",
                    content_hash="hash-one",
                    prompt_version=intake.DEFAULT_PAGE_EXTRACTION_PROMPT_VERSION,
                    ai_model=intake.DEFAULT_PAGE_EXTRACTION_MODEL,
                    ai_provider=intake.DEFAULT_PAGE_EXTRACTION_PROVIDER,
                    confidence=0.9,
                ),
                Record(
                    id=uuid4(),
                    document_id=document_id,
                    page_number=2,
                    summary="Completed page two",
                    content_hash="hash-two",
                    prompt_version=intake.DEFAULT_PAGE_EXTRACTION_PROMPT_VERSION,
                    ai_model=intake.DEFAULT_PAGE_EXTRACTION_MODEL,
                    ai_provider=intake.DEFAULT_PAGE_EXTRACTION_PROVIDER,
                    confidence=0.91,
                ),
                Record(
                    id=uuid4(),
                    document_id=document_id,
                    page_number=3,
                    summary="Stale prompt page three",
                    content_hash="hash-three",
                    prompt_version="old_prompt",
                    ai_model=intake.DEFAULT_PAGE_EXTRACTION_MODEL,
                    ai_provider=intake.DEFAULT_PAGE_EXTRACTION_PROVIDER,
                    confidence=0.7,
                ),
            ]
            self.progress_calls: list[tuple[object, dict[str, object]]] = []

        def list_page_summaries(self, document_id):
            return list(self.summaries)

        def update_extraction_job_progress(self, document_id, **values):
            self.progress_calls.append((document_id, values))
            return Record(stage="pages_extracting", **values)

    backend = Backend()
    monkeypatch.setattr(
        intake,
        "_load_completed_pages_backend",
        lambda: backend,
    )

    completed_lookup = asyncio.run(
        intake.activity_list_completed_pages(
            {
                "document_id": str(document_id),
                "total_pages": "4",
                "page_numbers": "1,2,3,4",
                "content_hash_1": "hash-one",
                "content_hash_2": "hash-two",
                "content_hash_3": "hash-three",
                "prompt_version": intake.DEFAULT_PAGE_EXTRACTION_PROMPT_VERSION,
                "ai_model": intake.DEFAULT_PAGE_EXTRACTION_MODEL,
                "ai_provider": intake.DEFAULT_PAGE_EXTRACTION_PROVIDER,
            }
        )
    )
    completed_by_number = intake_workflow._completed_pages_by_number(completed_lookup)

    remaining = intake_workflow._pages_to_extract(
        [1, 2, 3, 4],
        completed_by_number,
    )

    assert completed_lookup["completed_page_numbers"] == [1, 2]
    assert completed_lookup["skipped_count"] == 2
    assert remaining == [3, 4]
    assert backend.progress_calls[-1][1]["pages_completed"] == 2
    assert backend.progress_calls[-1][1]["current_page_excerpt"] == {
        "cache_status": "skipped_completed",
        "skipped_page_numbers": [1, 2],
    }


def test_page_activity_second_same_request_uses_cache_without_provider(
    monkeypatch,
) -> None:
    document_id = uuid4()
    provider_calls: list[dict[str, object]] = []

    class CountingExtractor:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

        async def _ai_extract_page(self, **kwargs):
            provider_calls.append(kwargs)
            return {
                "summary": "Generated page summary",
                "key_points": ["Point one"],
                "highlights": [],
                "places": [],
                "confidence": 0.88,
                "ai_token_usage": {"total_tokens": 42},
            }

        def _find_context_links(self, **kwargs):
            return []

    class Backend:
        PageSummaryExtractor = CountingExtractor

        def __init__(self) -> None:
            self.settings = SimpleNamespace(orderflow_ai_openai_api_key=None)
            self.summaries: list[Record] = []
            self.progress_calls: list[tuple[object, dict[str, object]]] = []

        def get_cached_page_summary(self, **kwargs):
            for summary in self.summaries:
                if (
                    summary.document_id == kwargs["document_id"]
                    and summary.page_number == kwargs["page_number"]
                    and summary.content_hash == kwargs["content_hash"]
                    and summary.prompt_version == kwargs["prompt_version"]
                    and summary.ai_model == kwargs["ai_model"]
                    and summary.ai_provider == kwargs["ai_provider"]
                ):
                    return summary
            return None

        def calculate_page_content_hash(self, page_text):
            return f"hash:{page_text}"

        def list_page_summaries(self, document_id):
            return list(self.summaries)

        def list_persisted_clauses(self, **kwargs):
            return []

        def list_persisted_obligations(self, document_id):
            return []

        def build_extracted_places(self, places, *, page_number):
            return []

        def geocode_places(self, places):
            return []

        def upsert_page_summary(self, **kwargs):
            summary = Record(id=uuid4(), **kwargs)
            self.summaries = [
                existing
                for existing in self.summaries
                if existing.page_number != kwargs["page_number"]
            ]
            self.summaries.append(summary)
            return summary

        def update_extraction_job_progress(self, document_id, **values):
            self.progress_calls.append((document_id, values))
            return Record(stage="pages_extracting", **values)

        def fail_extraction_job(self, document_id, **values):
            return Record(stage="pages_extracting", error=values)

    backend = Backend()
    monkeypatch.setattr(
        intake,
        "_load_page_extraction_backend",
        lambda: backend,
    )

    payload = {
        "document_id": str(document_id),
        "page_number": 2,
        "page_text": "Same page text for cache reuse.",
        "total_pages": 5,
    }

    first = asyncio.run(intake.activity_extract_page_cached(payload))
    second = asyncio.run(intake.activity_extract_page_cached(payload))

    assert first["cache_status"] == "miss_generated"
    assert second["cache_status"] == "hit"
    assert provider_calls == [
        {
            "page_num": 2,
            "page_text": "Same page text for cache reuse.",
            "total_pages": 5,
        }
    ]
    assert second["summary"] == "Generated page summary"
    assert second["summary_id"] == first["summary_id"]
    assert len(backend.summaries) == 1
    assert backend.progress_calls[-1][1]["current_page_excerpt"]["cache_status"] == "hit"


def test_page_activity_changed_prompt_version_calls_provider_again(
    monkeypatch,
) -> None:
    document_id = uuid4()
    provider_calls: list[dict[str, object]] = []

    class CountingExtractor:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

        async def _ai_extract_page(self, **kwargs):
            provider_calls.append(kwargs)
            return {
                "summary": f"Generated page summary {len(provider_calls)}",
                "key_points": ["Point one"],
                "highlights": [],
                "places": [],
                "confidence": 0.88,
            }

        def _find_context_links(self, **kwargs):
            return []

    class Backend:
        PageSummaryExtractor = CountingExtractor

        def __init__(self) -> None:
            self.settings = SimpleNamespace(orderflow_ai_openai_api_key=None)
            self.summaries: list[Record] = []
            self.progress_calls: list[tuple[object, dict[str, object]]] = []

        def get_cached_page_summary(self, **kwargs):
            for summary in self.summaries:
                if (
                    summary.document_id == kwargs["document_id"]
                    and summary.page_number == kwargs["page_number"]
                    and summary.content_hash == kwargs["content_hash"]
                    and summary.prompt_version == kwargs["prompt_version"]
                    and summary.ai_model == kwargs["ai_model"]
                    and summary.ai_provider == kwargs["ai_provider"]
                ):
                    return summary
            return None

        def calculate_page_content_hash(self, page_text):
            return f"hash:{page_text}"

        def list_page_summaries(self, document_id):
            return list(self.summaries)

        def list_persisted_clauses(self, **kwargs):
            return []

        def list_persisted_obligations(self, document_id):
            return []

        def build_extracted_places(self, places, *, page_number):
            return []

        def geocode_places(self, places):
            return []

        def upsert_page_summary(self, **kwargs):
            summary = Record(id=uuid4(), **kwargs)
            self.summaries.append(summary)
            return summary

        def update_extraction_job_progress(self, document_id, **values):
            self.progress_calls.append((document_id, values))
            return Record(stage="pages_extracting", **values)

        def fail_extraction_job(self, document_id, **values):
            return Record(stage="pages_extracting", error=values)

    backend = Backend()
    monkeypatch.setattr(
        intake,
        "_load_page_extraction_backend",
        lambda: backend,
    )

    base_payload = {
        "document_id": str(document_id),
        "page_number": 2,
        "page_text": "Same page text, changed prompt.",
        "total_pages": 5,
    }
    changed_prompt_payload = {
        **base_payload,
        "prompt_version": "intake_page_extraction_v2_0",
    }

    first = asyncio.run(intake.activity_extract_page_cached(base_payload))
    second = asyncio.run(intake.activity_extract_page_cached(changed_prompt_payload))

    assert first["cache_status"] == "miss_generated"
    assert second["cache_status"] == "miss_generated"
    assert len(provider_calls) == 2
    assert first["summary_id"] != second["summary_id"]
    assert first["prompt_version"] == intake.DEFAULT_PAGE_EXTRACTION_PROMPT_VERSION
    assert second["prompt_version"] == "intake_page_extraction_v2_0"
    assert len(backend.summaries) == 2
    assert {summary.prompt_version for summary in backend.summaries} == {
        intake.DEFAULT_PAGE_EXTRACTION_PROMPT_VERSION,
        "intake_page_extraction_v2_0",
    }


def test_page_activity_updates_progress_on_cache_hit(monkeypatch, caplog) -> None:
    document_id = uuid4()

    class Backend:
        def __init__(self) -> None:
            self.cached = Record(
                id=uuid4(),
                document_id=document_id,
                page_number=2,
                summary="Cached page summary",
                source_excerpt="cached source excerpt",
                content_hash="hash-two",
                confidence=0.91,
                ai_model="gpt-4o",
                ai_provider="openai",
            )
            self.summaries = [
                Record(page_number=1),
                Record(page_number=2),
            ]
            self.progress_calls: list[tuple[object, dict[str, object]]] = []

        def get_cached_page_summary(self, **kwargs):
            return self.cached

        def list_page_summaries(self, document_id):
            return list(self.summaries)

        def update_extraction_job_progress(self, document_id, **values):
            self.progress_calls.append((document_id, values))
            return Record(stage="pages_extracting", **values)

    backend = Backend()
    monkeypatch.setattr(
        intake,
        "_load_page_extraction_backend",
        lambda: backend,
    )

    with caplog.at_level(logging.INFO, logger=intake.__name__):
        result = asyncio.run(
            intake.activity_extract_page_cached(
                {
                    "document_id": str(document_id),
                    "page_number": 2,
                    "content_hash": "hash-two",
                    "prompt_version": (intake.DEFAULT_PAGE_EXTRACTION_PROMPT_VERSION),
                    "total_pages": 5,
                }
            )
        )

    assert result["cache_status"] == "hit"
    assert result["job_progress"]["pages_completed"] == 2
    assert result["job_progress"]["pages_total"] == 5
    assert result["job_progress"]["current_page"] == 2
    excerpt = backend.progress_calls[-1][1]["current_page_excerpt"]
    assert excerpt["cache_status"] == "hit"
    assert excerpt["content_hash"] == "hash-two"
    cache_logs = [
        record for record in caplog.records if record.message == "orderflow_worker_cache_hit"
    ]
    assert len(cache_logs) == 1
    assert cache_logs[0].orderflow == {
        "orderflow.document_id": str(document_id),
        "orderflow.workflow.stage": "pages_extracting",
        "orderflow.cache.status": "hit",
        "orderflow.cache.resource": "page_summary",
        "orderflow.prompt_version": intake.DEFAULT_PAGE_EXTRACTION_PROMPT_VERSION,
        "orderflow.ai_provider": intake.DEFAULT_PAGE_EXTRACTION_PROVIDER,
        "orderflow.ai_model": intake.DEFAULT_PAGE_EXTRACTION_MODEL,
        "orderflow.page_number": 2,
        "orderflow.summary_id": str(backend.cached.id),
    }
    assert "Cached page summary" not in caplog.text
    assert "cached source excerpt" not in caplog.text


def test_page_activity_records_failure_without_deleting_completed_pages(
    monkeypatch,
) -> None:
    document_id = uuid4()

    class FailingExtractor:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

        async def _ai_extract_page(self, **kwargs):
            raise RuntimeError("provider timeout while extracting page")

        def _find_context_links(self, **kwargs):
            return []

    class Backend:
        PageSummaryExtractor = FailingExtractor

        def __init__(self) -> None:
            self.settings = SimpleNamespace(orderflow_ai_openai_api_key=None)
            self.summaries = [
                Record(id=uuid4(), page_number=1),
                Record(id=uuid4(), page_number=2),
            ]
            self.progress_calls: list[tuple[object, dict[str, object]]] = []
            self.fail_calls: list[tuple[object, dict[str, object]]] = []
            self.upserts: list[dict[str, object]] = []

        def get_cached_page_summary(self, **kwargs):
            return None

        def calculate_page_content_hash(self, page_text):
            return "hash-three"

        def list_page_summaries(self, document_id):
            return list(self.summaries)

        def list_persisted_clauses(self, **kwargs):
            return []

        def list_persisted_obligations(self, document_id):
            return []

        def upsert_page_summary(self, **kwargs):
            self.upserts.append(kwargs)
            return Record(id=uuid4(), **kwargs)

        def update_extraction_job_progress(self, document_id, **values):
            self.progress_calls.append((document_id, values))
            return Record(stage="pages_extracting", **values)

        def fail_extraction_job(self, document_id, **values):
            self.fail_calls.append((document_id, values))
            return Record(stage="pages_extracting", error=values)

    backend = Backend()
    monkeypatch.setattr(
        intake,
        "_load_page_extraction_backend",
        lambda: backend,
    )

    with pytest.raises(RuntimeError, match="provider timeout"):
        asyncio.run(
            intake.activity_extract_page_cached(
                {
                    "document_id": str(document_id),
                    "page_number": 3,
                    "page_text": ("Page three fails while calling the provider."),
                    "total_pages": 5,
                }
            )
        )

    assert len(backend.summaries) == 2
    assert not backend.upserts
    progress = backend.progress_calls[-1][1]
    assert progress["pages_completed"] == 2
    assert progress["current_page"] == 3
    assert progress["current_page_excerpt"]["cache_status"] == "failed"
    assert progress["current_page_excerpt"]["error_code"] == "ai_timeout"
    assert progress["current_page_excerpt"]["error_category"] == "timeout"
    assert progress["current_page_excerpt"]["partial_failure"] is True
    assert "2 of 5 pages were saved" in progress["current_page_excerpt"]["error_message"]
    assert "completed pages will be reused" in progress["current_page_excerpt"]["error_message"]
    assert backend.fail_calls[-1][1]["error_code"] == "ai_timeout"


def test_action_plan_partial_retry_promotes_only_extracted_items(
    monkeypatch,
) -> None:
    document_id = uuid4()
    existing_id = uuid4()
    extracted_id = uuid4()
    generation_metadata = {
        "action_plan_generation": {
            "prompt_version": intake.DEFAULT_ACTION_PLAN_PROMPT_VERSION,
            "ai_provider": intake.DEFAULT_ACTION_PLAN_PROVIDER,
            "ai_model": intake.DEFAULT_ACTION_PLAN_MODEL,
        }
    }
    missing_evidence_metadata = {
        **generation_metadata,
        "action_plan_source_evidence": {
            "status": "needs_human_review",
            "missing_fields": ["source_page", "source_excerpt", "confidence"],
            "page_number": None,
            "source_excerpt": None,
            "confidence": None,
        },
    }

    class Backend:
        IntakeAiOptions = object
        ParsedClause = object

        def __init__(self) -> None:
            self.stage = "action_plan_pending"
            self.updates: list[tuple[object, dict[str, object]]] = []
            self.audits: list[dict[str, object]] = []
            self.stage_updates: list[tuple[object, str]] = []
            self.obligations = [
                Record(
                    id=existing_id,
                    document_id=document_id,
                    title="Already promoted",
                    description="Already part of the action plan.",
                    action_plan_stage="in_action_plan",
                    nature_of_action="other",
                    confidence=0.8,
                    metadata=generation_metadata,
                ),
                Record(
                    id=extracted_id,
                    document_id=document_id,
                    title="File compliance report",
                    description="The state shall file a compliance report.",
                    action_plan_stage="extracted",
                    nature_of_action=None,
                    confidence=None,
                ),
            ]

        def list_persisted_obligations(self, document_id):
            return list(self.obligations)

        def list_persisted_clauses(self, document_id):
            return []

        def maybe_extract_obligations_with_ai(self, **kwargs):
            return Record(
                obligations=[],
                attempted=False,
                used_ai=False,
                reason=None,
            )

        def extract_obligations(self, **kwargs):
            return []

        def replace_document_extraction(self, **kwargs):
            return [], []

        def update_persisted_obligation(self, obligation_id, **values):
            self.updates.append((obligation_id, values))
            for obligation in self.obligations:
                if obligation.id != obligation_id:
                    continue
                updated = Record(**obligation.__dict__)
                for key, value in values.items():
                    setattr(updated, key, value)
                self.obligations = [
                    updated if item.id == obligation_id else item for item in self.obligations
                ]
                return updated
            return None

        def record_persisted_obligation_audit_event(self, **kwargs):
            self.audits.append(kwargs)

        def get_extraction_job(self, document_id):
            return Record(stage=self.stage)

        def update_extraction_job_stage(self, document_id, stage):
            self.stage = stage
            self.stage_updates.append((document_id, stage))
            return Record(stage=stage)

    backend = Backend()
    monkeypatch.setattr(intake, "_load_action_plan_backend", lambda: backend)

    first_result = asyncio.run(intake.activity_extract_action_plan(str(document_id)))
    second_result = asyncio.run(intake.activity_extract_action_plan(str(document_id)))

    assert first_result["cache_status"] == "miss_generated"
    assert first_result["action_item_count"] == 2
    assert second_result["cache_status"] == "hit"
    assert backend.updates == [
        (
            extracted_id,
            {
                "action_plan_stage": "in_action_plan",
                "nature_of_action": "compliance_report",
                "metadata": missing_evidence_metadata,
            },
        )
    ]
    assert len(backend.audits) == 1
    assert backend.stage_updates == [(document_id, "action_plan_done")]


def test_action_plan_generation_persists_items_as_lifecycle_obligations(
    monkeypatch,
) -> None:
    document_id = uuid4()
    clause_id = uuid4()
    persisted_id = uuid4()
    generation_metadata = {
        "action_plan_generation": {
            "prompt_version": intake.DEFAULT_ACTION_PLAN_PROMPT_VERSION,
            "ai_provider": intake.DEFAULT_ACTION_PLAN_PROVIDER,
            "ai_model": intake.DEFAULT_ACTION_PLAN_MODEL,
        }
    }
    ready_evidence_metadata = {
        **generation_metadata,
        "action_plan_source_evidence": {
            "status": "ready",
            "missing_fields": [],
            "page_number": 2,
            "source_excerpt": "The department shall pay arrears within 30 days.",
            "confidence": 0.91,
        },
    }

    class Backend:
        IntakeAiOptions = Record
        ParsedClause = Record

        def __init__(self) -> None:
            self.stage = "action_plan_pending"
            self.replaced = False
            self.updates: list[tuple[object, dict[str, object]]] = []
            self.stage_updates: list[tuple[object, str]] = []
            self.obligations: list[Record] = []

        def get_extraction_job(self, document_id):
            return Record(stage=self.stage)

        def list_persisted_obligations(self, document_id):
            return list(self.obligations)

        def list_persisted_clauses(self, document_id):
            return [
                Record(
                    id=clause_id,
                    document_id=document_id,
                    clause_index=1,
                    page_number=2,
                    span_start=10,
                    span_end=90,
                    text="The department shall pay arrears within 30 days.",
                    normalized_text="The department shall pay arrears within 30 days.",
                    confidence=0.88,
                )
            ]

        def maybe_extract_obligations_with_ai(self, **kwargs):
            assert kwargs["document_id"] == document_id
            assert kwargs["clauses"][0].page_number == 2
            return Record(
                obligations=[
                    Record(
                        id=uuid4(),
                        document_id=document_id,
                        title="Pay arrears",
                        description="The department shall pay arrears within 30 days.",
                        owner_hint="Education Department",
                        confidence=0.91,
                    )
                ],
                attempted=True,
                used_ai=True,
                reason=None,
            )

        def extract_obligations(self, **kwargs):
            raise AssertionError("AI result should avoid deterministic fallback")

        def replace_document_extraction(self, **kwargs):
            self.replaced = True
            persisted = Record(
                id=persisted_id,
                document_id=document_id,
                title=kwargs["obligations"][0].title,
                description=kwargs["obligations"][0].description,
                owner_hint=kwargs["obligations"][0].owner_hint,
                action_plan_stage="extracted",
                nature_of_action=None,
                review_state="pending_review",
                confidence=0.91,
                citation=SimpleNamespace(page_number=2),
                metadata={
                    "source_evidence": {
                        "page_number": 2,
                        "excerpt": "The department shall pay arrears within 30 days.",
                    }
                },
            )
            self.obligations = [persisted]
            return kwargs["clauses"], [persisted]

        def update_persisted_obligation(self, obligation_id, **values):
            self.updates.append((obligation_id, values))
            for obligation in self.obligations:
                if obligation.id != obligation_id:
                    continue
                updated = Record(**obligation.__dict__)
                for key, value in values.items():
                    setattr(updated, key, value)
                self.obligations = [
                    updated if item.id == obligation_id else item for item in self.obligations
                ]
                return updated
            return None

        def record_persisted_obligation_audit_event(self, **kwargs):
            return None

        def update_extraction_job_stage(self, document_id, stage):
            self.stage = stage
            self.stage_updates.append((document_id, stage))
            return Record(stage=stage)

    backend = Backend()
    monkeypatch.setattr(intake, "_load_action_plan_backend", lambda: backend)

    result = asyncio.run(intake.activity_extract_action_plan(str(document_id)))

    assert backend.replaced is True
    assert backend.updates == [
        (
            persisted_id,
            {
                "action_plan_stage": "in_action_plan",
                "nature_of_action": "payment",
                "metadata": ready_evidence_metadata,
            },
        )
    ]
    assert result["cache_status"] == "miss_generated"
    assert result["action_item_count"] == 1
    assert result["items"][0]["id"] == str(persisted_id)
    assert result["items"][0]["action_plan_stage"] == "in_action_plan"
    assert result["items"][0]["nature_of_action"] == "payment"
    assert backend.stage_updates == [(document_id, "action_plan_done")]


def test_action_plan_appeal_items_use_legal_review_guardrail(monkeypatch) -> None:
    document_id = uuid4()
    obligation_id = uuid4()
    source_excerpt = "The party may file appeal review petition within limitation."

    class Backend:
        IntakeAiOptions = object
        ParsedClause = object

        def __init__(self) -> None:
            self.stage = "action_plan_pending"
            self.updates: list[tuple[object, dict[str, object]]] = []
            self.obligations = [
                Record(
                    id=obligation_id,
                    document_id=document_id,
                    title="File appeal review petition",
                    description="File appeal review petition within limitation.",
                    action_plan_stage="extracted",
                    nature_of_action=None,
                    confidence=0.73,
                    citation=SimpleNamespace(page_number=6),
                    metadata={
                        "source_evidence": {
                            "page_number": 6,
                            "excerpt": source_excerpt,
                        }
                    },
                )
            ]

        def get_extraction_job(self, document_id):
            return Record(stage=self.stage)

        def list_persisted_obligations(self, document_id):
            return list(self.obligations)

        def list_persisted_clauses(self, document_id):
            return []

        def maybe_extract_obligations_with_ai(self, **kwargs):
            return Record(obligations=[], attempted=False, used_ai=False, reason=None)

        def extract_obligations(self, **kwargs):
            return []

        def replace_document_extraction(self, **kwargs):
            return [], []

        def update_persisted_obligation(self, obligation_id, **values):
            self.updates.append((obligation_id, values))
            updated = Record(**self.obligations[0].__dict__)
            for key, value in values.items():
                setattr(updated, key, value)
            self.obligations = [updated]
            return updated

        def record_persisted_obligation_audit_event(self, **kwargs):
            return None

        def update_extraction_job_stage(self, document_id, stage):
            self.stage = stage
            return Record(stage=stage)

    backend = Backend()
    monkeypatch.setattr(intake, "_load_action_plan_backend", lambda: backend)

    result = asyncio.run(intake.activity_extract_action_plan(str(document_id)))
    update_values = backend.updates[0][1]

    assert update_values["nature_of_action"] == "appeal_review"
    assert update_values["title"] == "Legal review for appeal or review remedy"
    assert "not final legal advice" in update_values["description"]
    assert "authorized legal counsel" in update_values["description"]
    assert "must file" not in update_values["description"].lower()
    assert (
        update_values["metadata"]["appeal_language_guardrail"]["status"]
        == "legal_review_required"
    )
    assert result["items"][0]["title"] == "Legal review for appeal or review remedy"
    assert "not final legal advice" in result["items"][0]["description"]


def test_action_plan_one_shot_when_job_done(monkeypatch) -> None:
    document_id = uuid4()
    extracted_id = uuid4()
    generation_metadata = {
        "action_plan_generation": {
            "prompt_version": intake.DEFAULT_ACTION_PLAN_PROMPT_VERSION,
            "ai_provider": intake.DEFAULT_ACTION_PLAN_PROVIDER,
            "ai_model": intake.DEFAULT_ACTION_PLAN_MODEL,
        }
    }

    class Backend:
        IntakeAiOptions = object
        ParsedClause = object

        def __init__(self) -> None:
            self.stage = "action_plan_done"
            self.obligations = [
                Record(
                    id=uuid4(),
                    document_id=document_id,
                    title="Existing action plan item",
                    description="Already approved item.",
                    action_plan_stage="approved",
                    nature_of_action="other",
                    confidence=0.8,
                    metadata=generation_metadata,
                ),
                Record(
                    id=extracted_id,
                    document_id=document_id,
                    title="Extra extracted item",
                    description="Leftover extracted item.",
                    action_plan_stage="extracted",
                    nature_of_action=None,
                    confidence=0.6,
                ),
            ]

        def get_extraction_job(self, document_id):
            return Record(stage=self.stage)

        def list_persisted_obligations(self, document_id):
            return list(self.obligations)

        def update_persisted_obligation(self, *_args, **_kwargs):
            raise AssertionError("Unexpected update on one-shot cache hit")

        def list_persisted_clauses(self, *_args, **_kwargs):
            raise AssertionError("Unexpected clause lookup on one-shot cache hit")

        def maybe_extract_obligations_with_ai(self, *_args, **_kwargs):
            raise AssertionError("Unexpected AI extraction on one-shot cache hit")

        def extract_obligations(self, *_args, **_kwargs):
            raise AssertionError("Unexpected deterministic extraction on one-shot cache hit")

        def replace_document_extraction(self, *_args, **_kwargs):
            raise AssertionError("Unexpected extraction replace on one-shot cache hit")

        def record_persisted_obligation_audit_event(self, *_args, **_kwargs):
            raise AssertionError("Unexpected audit on one-shot cache hit")

        def update_extraction_job_stage(self, *_args, **_kwargs):
            raise AssertionError("Unexpected stage update on one-shot cache hit")

    backend = Backend()
    monkeypatch.setattr(intake, "_load_action_plan_backend", lambda: backend)

    result = asyncio.run(intake.activity_extract_action_plan(str(document_id)))

    assert result["cache_status"] == "hit"
    assert result["action_item_count"] == 1
    assert result["job_stage"] == "action_plan_done"


def test_action_plan_one_shot_rejects_prompt_model_mismatch(monkeypatch) -> None:
    document_id = uuid4()

    class Backend:
        IntakeAiOptions = object
        ParsedClause = object

        def __init__(self) -> None:
            self.stage = "action_plan_done"
            self.obligations = [
                Record(
                    id=uuid4(),
                    document_id=document_id,
                    title="Existing action plan item",
                    description="Already generated item.",
                    action_plan_stage="approved",
                    nature_of_action="other",
                    confidence=0.8,
                    metadata={
                        "action_plan_generation": {
                            "prompt_version": "old_prompt",
                            "ai_provider": intake.DEFAULT_ACTION_PLAN_PROVIDER,
                            "ai_model": intake.DEFAULT_ACTION_PLAN_MODEL,
                        }
                    },
                )
            ]

        def get_extraction_job(self, document_id):
            return Record(stage=self.stage)

        def list_persisted_obligations(self, document_id):
            return list(self.obligations)

        def update_persisted_obligation(self, *_args, **_kwargs):
            raise AssertionError("Unexpected update on mismatched cache")

        def list_persisted_clauses(self, *_args, **_kwargs):
            raise AssertionError("Unexpected full regeneration on mismatch")

    backend = Backend()
    monkeypatch.setattr(intake, "_load_action_plan_backend", lambda: backend)

    with pytest.raises(ValueError, match="different prompt/model/provider"):
        asyncio.run(intake.activity_extract_action_plan(str(document_id)))


def test_action_plan_requires_summary_done_stage(monkeypatch) -> None:
    document_id = uuid4()

    class Backend:
        IntakeAiOptions = object
        ParsedClause = object

        def __init__(self) -> None:
            self.stage = "pages_done"

        def get_extraction_job(self, document_id):
            return Record(stage=self.stage)

        def list_persisted_obligations(self, document_id):
            raise AssertionError("Unexpected obligations lookup")

    backend = Backend()
    monkeypatch.setattr(intake, "_load_action_plan_backend", lambda: backend)

    with pytest.raises(ValueError, match="Summary must be completed"):
        asyncio.run(intake.activity_extract_action_plan(str(document_id)))
