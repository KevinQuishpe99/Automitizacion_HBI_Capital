from __future__ import annotations

import logging

from app.application.jobs.ensure_asientos_contables_job import execute_ensure_asientos_contables_job
from app.application.jobs.graph_workflow_context import init_graph_for_job
from app.workflows.wf import wf

logger = logging.getLogger(__name__)


@wf.step
async def ensure_asientos_contables_step(*, job_id: str) -> None:
    graph = init_graph_for_job()
    await execute_ensure_asientos_contables_job(job_id, graph)


@wf.workflow
async def ensure_asientos_contables_workflow(*, job_id: str) -> None:
    logger.info("ensure_asientos_contables workflow started job_id=%s", job_id)
    await ensure_asientos_contables_step(job_id=job_id)
