from __future__ import annotations

from datetime import timedelta

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from orderflow_worker.activities.intake import parse_stub_activity
    from orderflow_worker.activities.intake import translate_document_if_needed_activity


@workflow.defn(name="orderflow-intake-workflow")
class IntakeWorkflow:
    @workflow.run
    async def run(self, payload: dict[str, str]) -> dict[str, str]:
        translation_context = await workflow.execute_activity(
            translate_document_if_needed_activity,
            payload,
            start_to_close_timeout=timedelta(seconds=30),
        )

        parsed = await workflow.execute_activity(
            parse_stub_activity,
            translation_context,
            start_to_close_timeout=timedelta(seconds=30),
        )

        return {
            "document_id": parsed.get("document_id", "unknown"),
            "state": "done",
            "parse_stub": "ok",
            "source_language": parsed.get("source_language", "en"),
            "translation_status": parsed.get("translation_status", "not_required"),
        }
