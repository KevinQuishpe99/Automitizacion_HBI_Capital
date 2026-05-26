from __future__ import annotations

from app.application.jobs.graph_workflow_context import init_graph_for_job
from app.application.jobs.validate_payment_report_job import execute_validate_payment_report_job


async def execute_validate_payment_report_job_with_graph(job_id: str) -> None:
    graph = init_graph_for_job()
    await execute_validate_payment_report_job(job_id, graph)
