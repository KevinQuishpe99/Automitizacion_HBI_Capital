from __future__ import annotations

import logging

from app.application.jobs.graph_workflow_context import init_graph_for_job
from app.application.jobs.merge_composite_validado_pdfs_job import (
    execute_merge_composite_validado_pdfs_job,
)
from app.workflows.wf import wf

logger = logging.getLogger(__name__)


@wf.step
async def merge_composite_validado_pdfs_step(
    *,
    job_id: str,
    force_rebuild: bool = False,
) -> None:
    graph = init_graph_for_job()
    await execute_merge_composite_validado_pdfs_job(
        job_id, graph, force_rebuild=force_rebuild
    )


@wf.workflow
async def merge_composite_validado_pdfs_workflow(
    *,
    job_id: str,
    force_rebuild: bool = False,
) -> None:
    logger.info("merge_composite_validado_pdfs workflow started job_id=%s", job_id)
    await merge_composite_validado_pdfs_step(job_id=job_id, force_rebuild=force_rebuild)
