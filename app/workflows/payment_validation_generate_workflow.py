from __future__ import annotations

import logging

from app.application.jobs.graph_workflow_context import init_graph_for_job
from app.application.jobs.payment_validation_generate_job import (
    execute_payment_validation_generate_job,
)
from app.workflows.wf import wf

logger = logging.getLogger(__name__)


@wf.step
async def payment_validation_generate_step(
    *,
    job_id: str,
    process_date_iso: str,
) -> None:
    graph = init_graph_for_job()
    await execute_payment_validation_generate_job(
        job_id, graph, process_date_iso=process_date_iso
    )


@wf.workflow
async def payment_validation_generate_workflow(
    *,
    job_id: str,
    process_date_iso: str,
) -> None:
    logger.info("payment_validation_generate workflow started job_id=%s", job_id)
    await payment_validation_generate_step(
        job_id=job_id, process_date_iso=process_date_iso
    )
