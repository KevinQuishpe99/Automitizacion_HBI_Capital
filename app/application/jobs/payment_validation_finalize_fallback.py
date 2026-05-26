from __future__ import annotations

from app.application.jobs.graph_workflow_context import init_graph_for_job
from app.application.jobs.payment_validation_finalize_job import (
    execute_payment_validation_finalize_job,
)


async def execute_payment_validation_finalize_job_with_graph(
    job_id: str,
    *,
    validation_file: str | None,
    validation_file_path: str | None,
    process_date_iso: str,
) -> None:
    graph = init_graph_for_job()
    await execute_payment_validation_finalize_job(
        job_id,
        graph,
        validation_file=validation_file,
        validation_file_path=validation_file_path,
        process_date_iso=process_date_iso,
    )
