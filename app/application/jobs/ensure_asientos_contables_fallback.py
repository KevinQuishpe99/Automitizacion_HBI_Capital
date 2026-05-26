from __future__ import annotations

from app.application.jobs.ensure_asientos_contables_job import execute_ensure_asientos_contables_job
from app.application.jobs.graph_workflow_context import init_graph_for_job


async def execute_ensure_asientos_contables_job_with_graph(job_id: str) -> None:
    graph = init_graph_for_job()
    await execute_ensure_asientos_contables_job(job_id, graph)
