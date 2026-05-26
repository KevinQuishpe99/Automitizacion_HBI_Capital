from __future__ import annotations

import logging

from app.application.jobs.graph_workflow_context import init_graph_for_job
from app.application.jobs.validate_payment_report_job import execute_validate_payment_report_job
from app.workflows.wf import wf

logger = logging.getLogger(__name__)


@wf.step
async def validate_payment_report_step(*, job_id: str) -> None:
    graph = init_graph_for_job()
    await execute_validate_payment_report_job(job_id, graph)


@wf.workflow
async def validate_payment_report_workflow(*, job_id: str) -> None:
    logger.info("validate_payment_report workflow started job_id=%s", job_id)
    await validate_payment_report_step(job_id=job_id)
