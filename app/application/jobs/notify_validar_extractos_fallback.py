from __future__ import annotations

from app.application.jobs.graph_workflow_context import init_graph_for_job
from app.application.jobs.notify_validar_extractos_job import execute_notify_validar_extractos_job


async def execute_notify_validar_extractos_job_with_graph(
    job_id: str,
    *,
    historical_file_path: str | None = None,
    to_override: str | None = None,
    cc_override: str | None = None,
) -> None:
    graph = init_graph_for_job()
    await execute_notify_validar_extractos_job(
        job_id,
        graph,
        historical_file_path=historical_file_path,
        to_override=to_override,
        cc_override=cc_override,
    )
