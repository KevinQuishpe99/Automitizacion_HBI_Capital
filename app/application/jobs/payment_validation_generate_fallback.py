from __future__ import annotations

from app.application.jobs.graph_workflow_context import init_graph_for_job
from app.application.jobs.payment_validation_generate_job import (
    execute_payment_validation_generate_job,
)


async def execute_payment_validation_generate_job_with_graph(
    job_id: str,
    *,
    process_date_iso: str,
) -> None:
    graph = init_graph_for_job()
    await execute_payment_validation_generate_job(
        job_id, graph, process_date_iso=process_date_iso
    )
