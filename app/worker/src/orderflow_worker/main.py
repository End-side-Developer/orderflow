from __future__ import annotations

import asyncio

from temporalio.client import Client
from temporalio.worker import Worker

from orderflow_worker.activities.intake import (
    activity_extract_action_plan,
    activity_generate_full_summary,
    activity_extract_page_cached,
    activity_list_completed_pages,
    activity_mark_intake_stage,
    activity_pause_intake_job,
    activity_resume_intake_job,
    translate_document_if_needed_activity,
)
from orderflow_worker.core.config import settings
from orderflow_worker.workflows.intake import IntakeWorkflow


async def run_worker() -> None:
    client = await Client.connect(
        settings.orderflow_worker_temporal_host,
        namespace=settings.orderflow_worker_temporal_namespace,
    )

    worker = Worker(
        client,
        task_queue=settings.orderflow_worker_task_queue,
        workflows=[IntakeWorkflow],
        activities=[
            activity_extract_action_plan,
            activity_generate_full_summary,
            activity_extract_page_cached,
            activity_list_completed_pages,
            activity_mark_intake_stage,
            activity_pause_intake_job,
            activity_resume_intake_job,
            translate_document_if_needed_activity,
        ],
    )
    await worker.run()


def run() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    run()
