from __future__ import annotations

from app.application.jobs.graph_workflow_context import init_graph_for_job
from app.application.jobs.merge_composite_validado_pdfs_job import (
    execute_merge_composite_validado_pdfs_job,
)


async def execute_merge_composite_validado_pdfs_job_with_graph(
    job_id: str,
    *,
    force_rebuild: bool = False,
) -> None:
    graph = init_graph_for_job()
    await execute_merge_composite_validado_pdfs_job(
        job_id, graph, force_rebuild=force_rebuild
    )
