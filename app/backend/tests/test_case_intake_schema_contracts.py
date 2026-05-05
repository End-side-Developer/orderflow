from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from orderflow_api.schemas.cases import (
    ActionPlanItemRegenerateData,
    ActionPlanItemRegenerateEnvelope,
    ActionPlanItemRegenerateRequest,
    ActionPlanItemReviewData,
    ActionPlanItemReviewEnvelope,
    ActionPlanItemReviewRequest,
    CaseFinalizeData,
    CaseFinalizeEnvelope,
    CaseFinalizeRequest,
    DocumentSummaryCaseBasics,
    DocumentSummaryData,
    DocumentSummaryDirective,
    DocumentSummaryEnvelope,
    DocumentSummaryFlowEdge,
    DocumentSummaryFlowGraph,
    DocumentSummaryFlowNode,
    DocumentSummaryImportantDate,
    DocumentSummaryMapData,
    DocumentSummaryResponsibleDepartment,
    DocumentSummarySourceEvidence,
    ExtractionJobStatusData,
    ExtractionJobStatusEnvelope,
)


def test_extraction_job_status_contract_shape() -> None:
    document_id = uuid4()
    job_id = uuid4()
    now = datetime.now(UTC)

    envelope = ExtractionJobStatusEnvelope(
        message="intake_status",
        data=ExtractionJobStatusData(
            id=job_id,
            document_id=document_id,
            stage="pages_extracting",
            pages_total=16,
            pages_completed=4,
            current_page=5,
            current_page_excerpt={
                "page_number": 5,
                "text": "short excerpt",
                "cache_status": "hit",
            },
            percent=25.0,
            status_message="Rate limit pause. Retrying in 60s.",
            current_page_cache_status="hit",
            is_paused=True,
            next_action="Continue to summary.",
            retry_after_seconds=60,
            paused_until=now,
            current_concurrency=1,
            started_at=now,
            updated_at=now,
        ),
    )

    payload = envelope.model_dump(mode="json")
    assert payload["ok"] is True
    assert payload["message"] == "intake_status"
    assert payload["data"]["document_id"] == str(document_id)
    assert payload["data"]["stage"] == "pages_extracting"
    assert payload["data"]["current_page_excerpt"]["page_number"] == 5
    assert payload["data"]["percent"] == 25.0
    assert payload["data"]["status_message"] == "Rate limit pause. Retrying in 60s."
    assert payload["data"]["current_page_cache_status"] == "hit"
    assert payload["data"]["is_paused"] is True
    assert payload["data"]["next_action"] == "Continue to summary."


def test_document_summary_contract_shape() -> None:
    document_id = uuid4()
    evidence = DocumentSummarySourceEvidence(
        page_number=2,
        paragraph_reference="para-12",
        source_excerpt="short source excerpt",
        confidence=0.92,
    )

    envelope = DocumentSummaryEnvelope(
        message="summary_ready",
        data=DocumentSummaryData(
            document_id=document_id,
            case_basics=DocumentSummaryCaseBasics(
                case_number="W.P.(C) sample",
                court_name="High Court",
                disposal_status="disposed",
                main_subject="service matter",
            ),
            overview="The court considered the grievance and issued directions.",
            key_directives=[
                DocumentSummaryDirective(
                    direction_text="Review the representation.",
                    source_page_number=2,
                    directive_kind="mandatory",
                    compliance_required="yes",
                    source_evidence=[evidence],
                )
            ],
            important_dates=[
                DocumentSummaryImportantDate(
                    label="Compliance deadline",
                    date_text="30 days",
                    is_inferred=False,
                    source_evidence=[evidence],
                )
            ],
            responsible_departments=[
                DocumentSummaryResponsibleDepartment(
                    primary_department="Education Department",
                    reason="Named respondent department",
                    source_evidence=[evidence],
                )
            ],
            flow_graph=DocumentSummaryFlowGraph(
                document_id=document_id,
                nodes=[
                    DocumentSummaryFlowNode(
                        id="order-1",
                        node_type="order",
                        label="Final direction",
                        page_ref=2,
                    )
                ],
                edges=[
                    DocumentSummaryFlowEdge(
                        id="edge-1",
                        source="order-1",
                        target="order-1",
                        relation="self",
                    )
                ],
                narrative_steps=["Court gave final direction"],
            ),
            map_data=DocumentSummaryMapData(
                available=False,
                reason="No meaningful location-based case flow was found.",
            ),
            confidence=0.88,
            prompt_version="summary-v1",
        ),
    )

    payload = envelope.model_dump(mode="json")
    assert payload["ok"] is True
    assert payload["data"]["case_basics"]["disposal_status"] == "disposed"
    assert payload["data"]["key_directives"][0]["compliance_required"] == "yes"
    assert payload["data"]["important_dates"][0]["is_inferred"] is False
    assert payload["data"]["flow_graph"]["nodes"][0]["node_type"] == "order"
    assert payload["data"]["map_data"]["available"] is False


def test_action_plan_item_review_request_contract_validation() -> None:
    assert ActionPlanItemReviewRequest(decision="approve").decision == "approve"
    assert (
        ActionPlanItemReviewRequest(
            decision="edit",
            edited_fields={"owner_hint": "Health Department"},
        ).edited_fields["owner_hint"]
        == "Health Department"
    )
    assert (
        ActionPlanItemReviewRequest(
            decision="reject",
            rejection_reason="Unsupported by citation",
        ).rejection_reason
        == "Unsupported by citation"
    )

    with pytest.raises(ValidationError):
        ActionPlanItemReviewRequest(decision="edit")

    with pytest.raises(ValidationError):
        ActionPlanItemReviewRequest(decision="reject")


def test_action_plan_item_review_response_contract_shape() -> None:
    document_id = uuid4()
    obligation_id = uuid4()
    reviewed_at = datetime.now(UTC)

    envelope = ActionPlanItemReviewEnvelope(
        message="item_reviewed",
        data=ActionPlanItemReviewData(
            document_id=document_id,
            obligation_id=obligation_id,
            decision="approve",
            action_plan_stage="approved",
            reviewer_name="Reviewer",
            reviewed_at=reviewed_at,
        ),
    )

    payload = envelope.model_dump(mode="json")
    assert payload["ok"] is True
    assert payload["message"] == "item_reviewed"
    assert payload["data"]["obligation_id"] == str(obligation_id)
    assert payload["data"]["action_plan_stage"] == "approved"


def test_action_plan_item_regenerate_contract_shape() -> None:
    document_id = uuid4()
    obligation_id = uuid4()

    request = ActionPlanItemRegenerateRequest(
        feedback="Use only the cited pages and correct the owner.",
        reviewer_name="Reviewer",
    )
    envelope = ActionPlanItemRegenerateEnvelope(
        message="item_regenerated",
        data=ActionPlanItemRegenerateData(
            document_id=document_id,
            obligation_id=obligation_id,
            action_plan_stage="review_pending",
            regen_count=2,
            updated_fields={"owner_hint": "Health Department"},
        ),
    )

    payload = envelope.model_dump(mode="json")
    assert request.feedback.startswith("Use only")
    assert payload["data"]["regen_count"] == 2
    assert payload["data"]["updated_fields"]["owner_hint"] == "Health Department"


def test_case_finalize_contract_shape() -> None:
    document_id = uuid4()

    request = CaseFinalizeRequest(reviewer_name="Reviewer", comments="Ready for dashboard")
    envelope = CaseFinalizeEnvelope(
        message="case_finalized",
        data=CaseFinalizeData(
            document_id=document_id,
            approved_count=3,
            edited_count=1,
            rejected_count=2,
            finalized_at=datetime.now(UTC),
        ),
    )

    payload = envelope.model_dump(mode="json")
    assert request.comments == "Ready for dashboard"
    assert payload["message"] == "case_finalized"
    assert payload["data"]["stage"] == "finalized"
    assert payload["data"]["approved_count"] == 3
