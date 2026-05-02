import json
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from orderflow_api.main import app
from orderflow_api.schemas.extractions import ClauseRecord
from orderflow_api.schemas.documents import (
    DocumentRecord,
    IndianECourtsCCMSEnvelope,
    IndianECourtsCISEnvelope,
    IndianECourtsIntakeRequest,
    IndianECourtsLookupRecord,
)
from orderflow_api.schemas.obligations import (
    ObligationCitation,
    ObligationConfidenceAnnotations,
    ObligationRecord,
)
from orderflow_api.schemas.workbench import (
    WorkbenchActivityItem,
    WorkbenchDocumentCard,
    WorkbenchDocumentData,
    WorkbenchDocumentMetrics,
    WorkbenchOverviewData,
    WorkbenchRelatedCase,
    WorkbenchSummary,
)
from orderflow_api.schemas.workflows import WorkflowRunRecord


client = TestClient(app)


def test_health_returns_request_and_trace_headers() -> None:
    response = client.get(
        "/health",
        headers={
            "x-request-id": "req-test-otel-001",
            "x-client-service": "orderflow-frontend",
            "x-client-path": "/health",
        },
    )

    assert response.status_code == 200
    assert response.headers["x-request-id"] == "req-test-otel-001"
    assert "x-trace-id" in response.headers
    assert len(response.headers["x-trace-id"]) == 32


def test_create_and_get_document_contract() -> None:
    create_response = client.post(
        "/api/v1/documents",
        json={
            "source_file_name": "sample-judgment.pdf",
            "source_file_type": "application/pdf",
            "source_file_size": 2048,
        },
    )

    assert create_response.status_code == 201
    payload = create_response.json()
    assert payload["ok"] is True
    assert payload["message"] == "document_created"
    assert payload["data"]["source_file_name"] == "sample-judgment.pdf"

    document_id = payload["data"]["id"]
    get_response = client.get(f"/api/v1/documents/{document_id}")

    assert get_response.status_code == 200
    get_payload = get_response.json()
    assert get_payload["ok"] is True
    assert get_payload["data"]["id"] == document_id


def test_download_document_contract(monkeypatch) -> None:
    now = datetime.now(UTC)
    document_id = uuid4()

    document = DocumentRecord(
        id=document_id,
        source_file_name="sample-judgment.pdf",
        source_file_type="application/pdf",
        source_file_size=18,
        object_key="documents/mock/sample-judgment.pdf",
        checksum_sha256="c" * 64,
        workflow_run_id=None,
        status="uploaded",
        metadata={"source": "test"},
        created_at=now,
        updated_at=now,
    )

    monkeypatch.setattr("orderflow_api.api.routes.documents.get_document", lambda _: None)
    monkeypatch.setattr(
        "orderflow_api.api.routes.documents.get_persisted_document",
        lambda _: document,
    )
    monkeypatch.setattr(
        "orderflow_api.api.routes.documents.get_object_bytes",
        lambda _client, _object_key: b"pdf bytes here",
    )

    response = client.get(f"/api/v1/documents/{document_id}/download")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/pdf")
    assert response.headers["content-disposition"] == ('attachment; filename="sample-judgment.pdf"')
    assert response.content == b"pdf bytes here"


def test_list_obligations_contract() -> None:
    create_response = client.post(
        "/api/v1/documents",
        json={
            "source_file_name": "obligation-source.pdf",
            "source_file_type": "application/pdf",
            "source_file_size": 8192,
        },
    )
    document_id = create_response.json()["data"]["id"]

    obligations_response = client.get(
        "/api/v1/obligations",
        params={"document_id": document_id},
    )

    assert obligations_response.status_code == 200
    payload = obligations_response.json()
    assert payload["ok"] is True
    assert payload["data"]["document_id"] == document_id
    assert payload["data"]["total"] >= 1
    assert len(payload["data"]["items"]) == payload["data"]["total"]


def test_export_action_plan_json_contract(monkeypatch) -> None:
    now = datetime.now(UTC)
    document_id = uuid4()

    document = DocumentRecord(
        id=document_id,
        source_file_name="export-source.pdf",
        source_file_type="application/pdf",
        source_file_size=1024,
        object_key="documents/mock/export-source.pdf",
        checksum_sha256="d" * 64,
        status="uploaded",
        metadata={"source": "test"},
        created_at=now,
        updated_at=now,
    )

    obligations = [
        ObligationRecord(
            id=uuid4(),
            document_id=document_id,
            obligation_code="OB-001",
            title="Submit compliance report",
            description="File monthly compliance report",
            owner_hint="District Officer",
            due_date=None,
            status="active",
            priority="high",
            review_state="pending_review",
            confidence=0.95,
            confidence_annotations=ObligationConfidenceAnnotations(
                extractor_version="deterministic-v1",
            ),
            citation=ObligationCitation(clause_span="p2:c4:s10-e64"),
            created_at=now,
            updated_at=now,
        )
    ]

    monkeypatch.setattr("orderflow_api.api.routes.exports.get_document", lambda _: None)
    monkeypatch.setattr(
        "orderflow_api.api.routes.exports.get_persisted_document",
        lambda _: document,
    )
    monkeypatch.setattr(
        "orderflow_api.api.routes.exports.list_persisted_obligations",
        lambda document_id=None: obligations,
    )

    response = client.get(
        "/api/v1/exports/action-plan",
        params={
            "document_id": str(document_id),
            "language": "en",
            "format": "json",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["message"] == "action_plan_export_ready"
    assert payload["data"]["document_id"] == str(document_id)
    assert payload["data"]["language"] == "en"
    assert payload["data"]["total"] == 1
    assert payload["data"]["items"][0]["title"] == "Submit compliance report"


def test_export_action_plan_markdown_contract(monkeypatch) -> None:
    now = datetime.now(UTC)
    document_id = uuid4()

    document = DocumentRecord(
        id=document_id,
        source_file_name="export-source.pdf",
        source_file_type="application/pdf",
        source_file_size=1024,
        object_key="documents/mock/export-source.pdf",
        checksum_sha256="e" * 64,
        status="uploaded",
        metadata={"source": "test"},
        created_at=now,
        updated_at=now,
    )

    obligations = [
        ObligationRecord(
            id=uuid4(),
            document_id=document_id,
            obligation_code="OB-002",
            title="Issue speaking order",
            description="Pass a reasoned order within 14 days",
            owner_hint="Case Officer",
            due_date=None,
            status="active",
            priority="critical",
            review_state="pending_review",
            confidence=0.91,
            confidence_annotations=ObligationConfidenceAnnotations(
                extractor_version="deterministic-v1",
            ),
            citation=ObligationCitation(clause_span="p3:c2:s4-e89"),
            created_at=now,
            updated_at=now,
        )
    ]

    monkeypatch.setattr("orderflow_api.api.routes.exports.get_document", lambda _: None)
    monkeypatch.setattr(
        "orderflow_api.api.routes.exports.get_persisted_document",
        lambda _: document,
    )
    monkeypatch.setattr(
        "orderflow_api.api.routes.exports.list_persisted_obligations",
        lambda document_id=None: obligations,
    )

    response = client.get(
        "/api/v1/exports/action-plan",
        params={
            "document_id": str(document_id),
            "language": "en",
            "format": "markdown",
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert f"action-plan-{document_id}-en.md" in response.headers["content-disposition"]
    assert "# Action Plan" in response.text
    assert "Issue speaking order" in response.text


def test_openapi_exposes_t11_a007_contract_paths() -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json().get("paths", {})
    assert "/api/v1/documents" in paths
    assert "/api/v1/documents/{document_id}" in paths
    assert "/api/v1/documents/{document_id}/download" in paths
    assert "/api/v1/documents/upload" in paths
    assert "/api/v1/documents/intake/indian-ecourts/lookup" in paths
    assert "/api/v1/documents/intake/indian-ecourts" in paths
    assert "/api/v1/exports/action-plan" in paths
    assert "/api/v1/extractions/intake/run" in paths
    assert "/api/v1/clauses" in paths
    assert "/api/v1/obligations" in paths
    assert "/api/v1/obligations/{obligation_id}" in paths
    assert "/api/v1/obligations/{obligation_id}/audit" in paths
    assert "/api/v1/escalations" in paths
    assert "/api/v1/workflows/intake/start" in paths
    assert "/api/v1/workflows/intake/status" in paths
    assert "/api/v1/workflows/runs/{run_id}" in paths
    assert "/api/v1/workbench/overview" in paths
    assert "/api/v1/workbench/documents/{document_id}" in paths


def test_workbench_overview_contract(monkeypatch) -> None:
    now = datetime.now(UTC)
    document_id = uuid4()

    overview = WorkbenchOverviewData(
        summary=WorkbenchSummary(
            total_documents=1,
            ready_documents=1,
            in_flight_documents=0,
            pending_review=2,
            open_escalations=1,
            critical_escalations=0,
            total_obligations=4,
        ),
        documents=[
            WorkbenchDocumentCard(
                document_id=document_id,
                source_file_name="case-a.pdf",
                source_language="en",
                status="ready",
                workflow_status="completed",
                pressure_level="watch",
                stage="review_gate",
                next_action="Resolve pending review items.",
                department="Law Department",
                court_name="Delhi High Court",
                created_at=now,
                updated_at=now,
                last_activity_at=now,
                metrics=WorkbenchDocumentMetrics(
                    total_obligations=4,
                    pending_review=2,
                    approved=1,
                    rejected=1,
                    completed=0,
                    open_escalations=1,
                    critical_escalations=0,
                ),
            )
        ],
        recent_activity=[
            WorkbenchActivityItem(
                title="Issue speaking order",
                document_id=document_id,
                obligation_id=uuid4(),
                action="obligation.review_state.updated",
                actor_type="reviewer",
                created_at=now,
                level="watch",
                detail="review state: approved",
            )
        ],
    )

    monkeypatch.setattr(
        "orderflow_api.api.routes.workbench.build_workbench_overview",
        lambda: overview,
    )

    response = client.get("/api/v1/workbench/overview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["message"] == "workbench_overview"
    assert payload["data"]["summary"]["pending_review"] == 2
    assert payload["data"]["documents"][0]["pressure_level"] == "watch"


def test_document_workbench_contract(monkeypatch) -> None:
    now = datetime.now(UTC)
    document_id = uuid4()

    workbench = WorkbenchDocumentData(
        document=WorkbenchDocumentCard(
            document_id=document_id,
            source_file_name="case-b.pdf",
            source_language="en",
            status="ready",
            workflow_status="completed",
            pressure_level="urgent",
            stage="execution_risk",
            next_action="Escalate breach-risk obligations.",
            department="Revenue",
            court_name="Madras High Court",
            created_at=now,
            updated_at=now,
            last_activity_at=now,
            metrics=WorkbenchDocumentMetrics(
                total_obligations=3,
                pending_review=0,
                approved=3,
                rejected=0,
                completed=1,
                open_escalations=2,
                critical_escalations=1,
            ),
        ),
        related_cases=[
            WorkbenchRelatedCase(
                document_id=uuid4(),
                source_file_name="precedent.pdf",
                similarity_score=0.76,
                overlap_count=4,
                rationale_tags=["pattern:compliance", "owner-overlap"],
                sample_titles=["Submit compliance report"],
                open_escalations=1,
                pressure_level="watch",
                recommended_focus="Compare reviewer handling.",
            )
        ],
        next_actions=[],
        recent_activity=[],
    )

    monkeypatch.setattr(
        "orderflow_api.api.routes.workbench.build_document_workbench",
        lambda _document_id: workbench,
    )

    response = client.get(f"/api/v1/workbench/documents/{document_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["message"] == "document_workbench"
    assert payload["data"]["document"]["stage"] == "execution_risk"
    assert payload["data"]["related_cases"][0]["similarity_score"] == 0.76


def test_upload_document_contract(monkeypatch) -> None:
    now = datetime.now(UTC)

    def fake_persist_uploaded_document(
        source_file_name: str,
        source_file_type: str | None,
        payload: bytes,
        metadata: dict[str, object] | None,
    ) -> DocumentRecord:
        return DocumentRecord(
            id=uuid4(),
            source_file_name=source_file_name,
            source_file_type=source_file_type,
            source_file_size=len(payload),
            object_key="documents/mock/sample.pdf",
            checksum_sha256="a" * 64,
            status="uploaded",
            metadata=metadata,
            created_at=now,
            updated_at=now,
        )

    monkeypatch.setattr(
        "orderflow_api.api.routes.documents.persist_uploaded_document",
        fake_persist_uploaded_document,
    )

    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("sample.pdf", b"dummy content", "application/pdf")},
        data={"metadata": '{"source":"test-suite"}'},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["ok"] is True
    assert payload["message"] == "document_uploaded"
    assert payload["data"]["object_key"] == "documents/mock/sample.pdf"


def test_intake_indian_ecourts_contract_with_ccms_and_cis(monkeypatch) -> None:
    now = datetime.now(UTC)

    def fake_persist_uploaded_document(
        source_file_name: str,
        source_file_type: str | None,
        payload: bytes,
        metadata: dict[str, object] | None,
    ) -> DocumentRecord:
        return DocumentRecord(
            id=uuid4(),
            source_file_name=source_file_name,
            source_file_type=source_file_type,
            source_file_size=len(payload),
            object_key="documents/mock/ecourts-sample.pdf",
            checksum_sha256="a" * 64,
            status="uploaded",
            metadata=metadata,
            created_at=now,
            updated_at=now,
        )

    monkeypatch.setattr(
        "orderflow_api.api.routes.documents.persist_uploaded_document",
        fake_persist_uploaded_document,
    )

    envelope = {
        "ccms": {
            "reference_id": "CCMS-REF-2026-001",
            "delivery_timestamp": "2026-04-24T10:15:00Z",
            "document_type": "final_order",
        },
        "cis": {
            "case_id": "CIS-CASE-2026-981",
            "court_name": "High Court of Karnataka",
            "court_code": "KAHC01",
            "order_date": "2026-04-20",
            "bench": "Division Bench",
            "parties": ["State of Karnataka", "Petitioner"],
            "case_type": "Writ Petition",
            "department_tags": ["Revenue", "Urban Development"],
        },
        "additional_metadata": {"delivery_feed": "nightly_sync"},
    }

    response = client.post(
        "/api/v1/documents/intake/indian-ecourts",
        files={"file": ("judgment.pdf", b"dummy content", "application/pdf")},
        data={"envelope": json.dumps(envelope)},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["ok"] is True
    assert payload["message"] == "indian_ecourts_document_ingested"
    assert payload["data"]["object_key"] == "documents/mock/ecourts-sample.pdf"
    assert payload["data"]["metadata"]["source_system"] == "indian_ecourts_service"
    assert payload["data"]["metadata"]["integration_mode"] == "read_only_downstream_adapter"
    assert payload["data"]["metadata"]["ccms"]["reference_id"] == "CCMS-REF-2026-001"
    assert payload["data"]["metadata"]["cis"]["case_id"] == "CIS-CASE-2026-981"


def test_lookup_indian_ecourts_contract(monkeypatch) -> None:
    now = datetime.now(UTC)

    def fake_lookup_indian_ecourts_prefill(identifier: str) -> IndianECourtsLookupRecord:
        return IndianECourtsLookupRecord(
            identifier=identifier,
            resolved_source_url="https://delhihighcourt.nic.in/app/showFileJudgment/mock.pdf",
            source_file_name="mock.pdf",
            source_file_type="application/pdf",
            file_content_base64="JVBERi0xLjQK",
            envelope=IndianECourtsIntakeRequest(
                ccms=IndianECourtsCCMSEnvelope(
                    reference_id="DHC-CCMS-AUTO-MOCK",
                    delivery_timestamp=now,
                    document_type="judgment",
                    source_url="https://delhihighcourt.nic.in/app/showFileJudgment/mock.pdf",
                    source_gateway="indian-ecourts-service",
                    receipt_id="DHC-EC-AUTO-MOCK",
                ),
                cis=IndianECourtsCISEnvelope(
                    case_id="W.P.(C) 8524/2025",
                    court_name="High Court of Delhi",
                    court_code="DHC",
                ),
                source_file_name="mock.pdf",
                source_file_type="application/pdf",
            ),
            note="mocked lookup",
        )

    monkeypatch.setattr(
        "orderflow_api.api.routes.documents.lookup_indian_ecourts_prefill",
        fake_lookup_indian_ecourts_prefill,
    )

    response = client.post(
        "/api/v1/documents/intake/indian-ecourts/lookup",
        json={"identifier": "W.P.(C) 8524/2025"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["message"] == "indian_ecourts_lookup_ready"
    assert payload["data"]["identifier"] == "W.P.(C) 8524/2025"
    assert payload["data"]["source_file_name"] == "mock.pdf"
    assert payload["data"]["envelope"]["ccms"]["reference_id"] == "DHC-CCMS-AUTO-MOCK"


def test_intake_indian_ecourts_contract_with_ccms_only(monkeypatch) -> None:
    now = datetime.now(UTC)

    def fake_persist_uploaded_document(
        source_file_name: str,
        source_file_type: str | None,
        payload: bytes,
        metadata: dict[str, object] | None,
    ) -> DocumentRecord:
        return DocumentRecord(
            id=uuid4(),
            source_file_name=source_file_name,
            source_file_type=source_file_type,
            source_file_size=len(payload),
            object_key="documents/mock/ecourts-ccms-only.pdf",
            checksum_sha256="b" * 64,
            status="uploaded",
            metadata=metadata,
            created_at=now,
            updated_at=now,
        )

    monkeypatch.setattr(
        "orderflow_api.api.routes.documents.persist_uploaded_document",
        fake_persist_uploaded_document,
    )

    envelope = {
        "ccms": {
            "reference_id": "CCMS-REF-2026-002",
            "document_type": "judgment_pdf",
        },
        "additional_metadata": {"source": "ccms_pull"},
    }

    response = client.post(
        "/api/v1/documents/intake/indian-ecourts",
        files={"file": ("ccms-order.pdf", b"dummy content", "application/pdf")},
        data={"envelope": json.dumps(envelope)},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["ok"] is True
    assert payload["message"] == "indian_ecourts_document_ingested"
    assert payload["data"]["metadata"]["ccms"]["reference_id"] == "CCMS-REF-2026-002"
    assert "cis" not in payload["data"]["metadata"]


def test_start_intake_workflow_contract(monkeypatch) -> None:
    now = datetime.now(UTC)
    document_id = uuid4()
    expected_run_id = "run-123"

    document = DocumentRecord(
        id=document_id,
        source_file_name="sample.txt",
        source_file_type="text/plain",
        source_file_size=12,
        object_key="documents/mock/sample.txt",
        checksum_sha256="b" * 64,
        workflow_run_id=None,
        status="uploaded",
        metadata={"source": "test"},
        created_at=now,
        updated_at=now,
    )

    class FakeHandle:
        run_id = expected_run_id

    class FakeTemporalClient:
        async def start_workflow(self, *args, **kwargs):  # noqa: ANN002, ANN003
            assert args[0] == "orderflow-intake-workflow"
            assert kwargs["task_queue"] == "orderflow-default"
            return FakeHandle()

    async def fake_get_temporal_client() -> FakeTemporalClient:
        return FakeTemporalClient()

    def fake_record_workflow_run(
        document_id,  # noqa: ANN001
        workflow_type,  # noqa: ANN001
        workflow_id,  # noqa: ANN001
        run_id,  # noqa: ANN001
        task_queue,  # noqa: ANN001
        status,  # noqa: ANN001
        metadata,  # noqa: ANN001
    ) -> WorkflowRunRecord:
        return WorkflowRunRecord(
            id=uuid4(),
            document_id=document_id,
            workflow_type=workflow_type,
            workflow_id=workflow_id,
            run_id=run_id,
            task_queue=task_queue,
            status=status,
            metadata=metadata,
            started_at=now,
            completed_at=None,
            created_at=now,
            updated_at=now,
        )

    captured: dict[str, str] = {}

    def fake_set_document_workflow_run_id(document_id, workflow_run_id):  # noqa: ANN001
        captured["document_id"] = str(document_id)
        captured["workflow_run_id"] = workflow_run_id

    monkeypatch.setattr(
        "orderflow_api.api.routes.workflows.get_persisted_document",
        lambda value: document if value == document_id else None,
    )
    monkeypatch.setattr(
        "orderflow_api.api.routes.workflows.get_temporal_client",
        fake_get_temporal_client,
    )
    monkeypatch.setattr(
        "orderflow_api.api.routes.workflows.record_workflow_run",
        fake_record_workflow_run,
    )
    monkeypatch.setattr(
        "orderflow_api.api.routes.workflows.set_document_workflow_run_id",
        fake_set_document_workflow_run_id,
    )

    response = client.post(
        "/api/v1/workflows/intake/start",
        json={"document_id": str(document_id)},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["ok"] is True
    assert payload["message"] == "workflow_started"
    assert payload["data"]["document_id"] == str(document_id)
    assert payload["data"]["run_id"] == expected_run_id
    assert captured["workflow_run_id"] == expected_run_id


def test_get_intake_workflow_status_contract(monkeypatch) -> None:
    now = datetime.now(UTC)
    document_id = uuid4()
    run_id = "run-xyz"

    document = DocumentRecord(
        id=document_id,
        source_file_name="sample.txt",
        source_file_type="text/plain",
        source_file_size=12,
        object_key="documents/mock/sample.txt",
        checksum_sha256="f" * 64,
        workflow_run_id=run_id,
        status="processing",
        metadata={"source": "test"},
        created_at=now,
        updated_at=now,
    )

    run_record = WorkflowRunRecord(
        id=uuid4(),
        document_id=document_id,
        workflow_type="intake",
        workflow_id="orderflow-intake-workflow-1",
        run_id=run_id,
        task_queue="orderflow-default",
        status="started",
        metadata={"source": "api"},
        started_at=now,
        completed_at=None,
        created_at=now,
        updated_at=now,
    )

    monkeypatch.setattr(
        "orderflow_api.api.routes.workflows.get_persisted_document",
        lambda value: document if value == document_id else None,
    )
    monkeypatch.setattr(
        "orderflow_api.api.routes.workflows.get_workflow_run_by_run_id",
        lambda value: run_record if value == run_id else None,
    )

    class FakeHandle:
        async def describe(self):  # noqa: ANN201
            return SimpleNamespace(status=SimpleNamespace(name="RUNNING"), close_time=None)

    class FakeTemporalClient:
        def get_workflow_handle(self, *args, **kwargs):  # noqa: ANN002, ANN003
            return FakeHandle()

    async def fake_get_temporal_client() -> FakeTemporalClient:
        return FakeTemporalClient()

    monkeypatch.setattr(
        "orderflow_api.api.routes.workflows.get_temporal_client",
        fake_get_temporal_client,
    )

    response = client.get(
        "/api/v1/workflows/intake/status",
        params={"document_id": str(document_id)},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["message"] == "workflow_status"
    assert payload["data"]["document_id"] == str(document_id)
    assert payload["data"]["run_id"] == run_id


def test_get_workflow_run_by_id_contract(monkeypatch) -> None:
    now = datetime.now(UTC)
    run_id = "run-by-id"
    document_id = uuid4()

    run_record = WorkflowRunRecord(
        id=uuid4(),
        document_id=document_id,
        workflow_type="intake",
        workflow_id="orderflow-intake-workflow-2",
        run_id=run_id,
        task_queue="orderflow-default",
        status="started",
        metadata={"source": "api"},
        started_at=now,
        completed_at=None,
        created_at=now,
        updated_at=now,
    )

    monkeypatch.setattr(
        "orderflow_api.api.routes.workflows.get_workflow_run_by_run_id",
        lambda value: run_record if value == run_id else None,
    )

    class FakeHandle:
        async def describe(self):  # noqa: ANN201
            return SimpleNamespace(status=SimpleNamespace(name="RUNNING"), close_time=None)

    class FakeTemporalClient:
        def get_workflow_handle(self, *args, **kwargs):  # noqa: ANN002, ANN003
            return FakeHandle()

    async def fake_get_temporal_client() -> FakeTemporalClient:
        return FakeTemporalClient()

    monkeypatch.setattr(
        "orderflow_api.api.routes.workflows.get_temporal_client",
        fake_get_temporal_client,
    )

    response = client.get(f"/api/v1/workflows/runs/{run_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["message"] == "workflow_status"
    assert payload["data"]["run_id"] == run_id


def test_run_intake_extraction_contract(monkeypatch) -> None:
    now = datetime.now(UTC)
    document_id = uuid4()

    persisted_document = DocumentRecord(
        id=document_id,
        source_file_name="sample-judgment.txt",
        source_file_type="text/plain",
        source_file_size=100,
        object_key="documents/mock/sample-judgment.txt",
        checksum_sha256="c" * 64,
        workflow_run_id=None,
        status="uploaded",
        metadata={"source": "test"},
        created_at=now,
        updated_at=now,
    )

    clause = ClauseRecord(
        id=uuid4(),
        document_id=document_id,
        clause_index=1,
        page_number=None,
        span_start=0,
        span_end=72,
        text="The respondent shall submit a compliance affidavit within 7 days.",
        normalized_text="The respondent shall submit a compliance affidavit within 7 days.",
        confidence=0.9,
        created_at=now,
        updated_at=now,
    )

    obligation = ObligationRecord(
        id=uuid4(),
        document_id=document_id,
        obligation_code="OBL-AUTO-001",
        title="The respondent shall submit a compliance affidavit within 7 days",
        description="The respondent shall submit a compliance affidavit within 7 days.",
        owner_hint="The respondent",
        due_date=None,
        status="draft",
        priority="high",
        review_state="pending_review",
        confidence=0.9,
        citation=ObligationCitation(page_number=None, clause_span="clause-1"),
        created_at=now,
        updated_at=now,
    )

    monkeypatch.setattr(
        "orderflow_api.api.routes.extractions.get_persisted_document",
        lambda value: persisted_document if value == document_id else None,
    )
    monkeypatch.setattr(
        "orderflow_api.api.routes.extractions.build_object_storage_client",
        lambda: object(),
    )

    def fake_get_object_bytes(client, object_key):  # noqa: ANN001
        return b"The respondent shall submit a compliance affidavit within 7 days."

    monkeypatch.setattr(
        "orderflow_api.api.routes.extractions.get_object_bytes",
        fake_get_object_bytes,
    )

    def fake_replace_document_extraction(document_id, clauses, obligations):  # noqa: ANN001
        return [clause], [obligation]

    monkeypatch.setattr(
        "orderflow_api.api.routes.extractions.replace_document_extraction",
        fake_replace_document_extraction,
    )

    response = client.post(
        "/api/v1/extractions/intake/run",
        json={"document_id": str(document_id)},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["message"] == "intake_extraction_completed"
    assert payload["data"]["document_id"] == str(document_id)
    assert payload["data"]["clause_count"] == 1
    assert payload["data"]["obligation_count"] == 1


def test_list_obligations_supports_persisted_records(monkeypatch) -> None:
    now = datetime.now(UTC)
    target_document_id = uuid4()

    persisted_document = DocumentRecord(
        id=target_document_id,
        source_file_name="sample-judgment.txt",
        source_file_type="text/plain",
        source_file_size=100,
        object_key="documents/mock/sample-judgment.txt",
        checksum_sha256="d" * 64,
        workflow_run_id=None,
        status="ready",
        metadata={"source": "test"},
        created_at=now,
        updated_at=now,
    )

    persisted_obligation = ObligationRecord(
        id=uuid4(),
        document_id=target_document_id,
        obligation_code="OBL-AUTO-001",
        title="Submit compliance affidavit",
        description="Respondent shall submit compliance affidavit.",
        owner_hint="Respondent",
        due_date=None,
        status="draft",
        priority="medium",
        review_state="pending_review",
        confidence=0.82,
        confidence_annotations=ObligationConfidenceAnnotations(
            extractor_version="structured-v1",
            components={"directive_signal": 1.0, "owner_signal": 1.0},
            weights={"directive_signal": 0.5, "owner_signal": 0.5},
            rationale=[],
            signals={"owner_detected": True},
        ),
        citation=ObligationCitation(page_number=None, clause_span="clause-1"),
        created_at=now,
        updated_at=now,
    )

    monkeypatch.setattr(
        "orderflow_api.api.routes.obligations.get_document",
        lambda value: None,
    )
    monkeypatch.setattr(
        "orderflow_api.api.routes.obligations.get_persisted_document",
        lambda value: persisted_document if value == target_document_id else None,
    )

    def fake_list_persisted_obligations(document_id=None):  # noqa: ANN001
        return [persisted_obligation] if document_id == target_document_id else []

    monkeypatch.setattr(
        "orderflow_api.api.routes.obligations.list_persisted_obligations",
        fake_list_persisted_obligations,
    )

    response = client.get(
        "/api/v1/obligations",
        params={"document_id": str(target_document_id)},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["data"]["total"] == 1
    assert payload["data"]["items"][0]["title"] == "Submit compliance affidavit"
    assert payload["data"]["items"][0]["confidence_annotations"]["extractor_version"] == (
        "structured-v1"
    )


def test_list_clauses_supports_persisted_filters(monkeypatch) -> None:
    now = datetime.now(UTC)
    target_document_id = uuid4()

    persisted_document = DocumentRecord(
        id=target_document_id,
        source_file_name="sample-judgment.txt",
        source_file_type="text/plain",
        source_file_size=100,
        object_key="documents/mock/sample-judgment.txt",
        checksum_sha256="e" * 64,
        workflow_run_id=None,
        status="ready",
        metadata={"source": "test"},
        created_at=now,
        updated_at=now,
    )

    clause_page_2 = ClauseRecord(
        id=uuid4(),
        document_id=target_document_id,
        clause_index=1,
        page_number=2,
        span_start=120,
        span_end=260,
        text="District Administration shall constitute implementation committee.",
        normalized_text="District Administration shall constitute implementation committee.",
        citation_span="p2:c1:120-260",
        confidence=0.86,
        created_at=now,
        updated_at=now,
    )
    clause_page_3 = ClauseRecord(
        id=uuid4(),
        document_id=target_document_id,
        clause_index=2,
        page_number=3,
        span_start=310,
        span_end=420,
        text="Government Counsel Office must file progress affidavit.",
        normalized_text="Government Counsel Office must file progress affidavit.",
        citation_span="p3:c2:310-420",
        confidence=0.82,
        created_at=now,
        updated_at=now,
    )

    monkeypatch.setattr(
        "orderflow_api.api.routes.obligations.get_document",
        lambda value: None,
    )
    monkeypatch.setattr(
        "orderflow_api.api.routes.obligations.get_persisted_document",
        lambda value: persisted_document if value == target_document_id else None,
    )

    def fake_list_persisted_clauses(  # noqa: ANN001
        document_id,
        page_number=None,
        clause_span=None,
    ):
        if document_id != target_document_id:
            return []
        if clause_span == "p3:c2:310-420":
            return [clause_page_3]
        if page_number == 2:
            return [clause_page_2]
        return [clause_page_2, clause_page_3]

    monkeypatch.setattr(
        "orderflow_api.api.routes.obligations.list_persisted_clauses",
        fake_list_persisted_clauses,
    )

    page_filtered_response = client.get(
        "/api/v1/clauses",
        params={"document_id": str(target_document_id), "page_number": 2},
    )
    assert page_filtered_response.status_code == 200
    page_payload = page_filtered_response.json()
    assert page_payload["ok"] is True
    assert page_payload["data"]["total"] == 1
    assert page_payload["data"]["items"][0]["citation_span"] == "p2:c1:120-260"

    span_filtered_response = client.get(
        "/api/v1/clauses",
        params={
            "document_id": str(target_document_id),
            "clause_span": "p3:c2:310-420",
        },
    )
    assert span_filtered_response.status_code == 200
    span_payload = span_filtered_response.json()
    assert span_payload["ok"] is True
    assert span_payload["data"]["total"] == 1
    assert span_payload["data"]["items"][0]["page_number"] == 3
    assert span_payload["data"]["items"][0]["clause_index"] == 2


def test_update_obligation_contract_for_stub_data() -> None:
    create_response = client.post(
        "/api/v1/documents",
        json={
            "source_file_name": "review-source.pdf",
            "source_file_type": "application/pdf",
            "source_file_size": 4096,
        },
    )
    assert create_response.status_code == 201
    document_id = create_response.json()["data"]["id"]

    obligations_response = client.get(
        "/api/v1/obligations",
        params={"document_id": document_id},
    )
    assert obligations_response.status_code == 200
    obligations_payload = obligations_response.json()
    assert obligations_payload["data"]["items"]
    obligation_id = obligations_payload["data"]["items"][0]["id"]

    update_response = client.patch(
        f"/api/v1/obligations/{obligation_id}",
        json={
            "review_state": "approved",
            "owner_hint": "Legal Compliance Cell",
            "status": "active",
        },
    )
    assert update_response.status_code == 200
    update_payload = update_response.json()
    assert update_payload["ok"] is True
    assert update_payload["message"] == "obligation_updated"
    assert update_payload["data"]["review_state"] == "approved"
    assert update_payload["data"]["owner_hint"] == "Legal Compliance Cell"
    assert update_payload["data"]["status"] == "active"


def test_list_escalations_contract_for_stub_data() -> None:
    create_response = client.post(
        "/api/v1/documents",
        json={
            "source_file_name": "escalation-source.pdf",
            "source_file_type": "application/pdf",
            "source_file_size": 2048,
        },
    )
    assert create_response.status_code == 201
    document_id = create_response.json()["data"]["id"]

    response = client.get(
        "/api/v1/escalations",
        params={"document_id": document_id},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["data"]["document_id"] == document_id
    assert payload["data"]["total"] == payload["data"]["open_total"]
    assert len(payload["data"]["items"]) == payload["data"]["total"]
    assert payload["data"]["critical_total"] >= 0

    if payload["data"]["items"]:
        first = payload["data"]["items"][0]
        assert first["obligation_id"]
        assert first["level"] in {"watch", "escalated", "critical"}
        assert isinstance(first["reasons"], list)


def test_get_obligation_audit_trail_after_update_contract() -> None:
    create_response = client.post(
        "/api/v1/documents",
        json={
            "source_file_name": "audit-source.pdf",
            "source_file_type": "application/pdf",
            "source_file_size": 3072,
        },
    )
    assert create_response.status_code == 201
    document_id = create_response.json()["data"]["id"]

    obligations_response = client.get(
        "/api/v1/obligations",
        params={"document_id": document_id},
    )
    assert obligations_response.status_code == 200
    obligation_id = obligations_response.json()["data"]["items"][0]["id"]

    update_response = client.patch(
        f"/api/v1/obligations/{obligation_id}",
        json={"owner_hint": "Case Monitoring Unit"},
    )
    assert update_response.status_code == 200

    audit_response = client.get(f"/api/v1/obligations/{obligation_id}/audit")
    assert audit_response.status_code == 200
    payload = audit_response.json()

    assert payload["ok"] is True
    assert payload["data"]["obligation_id"] == obligation_id
    assert payload["data"]["total"] >= 1
    assert len(payload["data"]["items"]) == payload["data"]["total"]

    owner_hint_updates = [
        event
        for event in payload["data"]["items"]
        if event["action"] == "obligation.owner_hint.updated"
    ]
    assert owner_hint_updates
    assert owner_hint_updates[-1]["payload"]["owner_hint"] == "Case Monitoring Unit"
