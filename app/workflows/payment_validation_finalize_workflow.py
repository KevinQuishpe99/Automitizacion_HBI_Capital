from __future__ import annotations

import logging

from app.application.jobs.graph_workflow_context import init_graph_for_job
from app.application.jobs.payment_validation_finalize_job import (
    execute_payment_validation_finalize_job,
)
from app.workflows.wf import wf

logger = logging.getLogger(__name__)


@wf.step
async def payment_validation_finalize_step(
    *,
    job_id: str,
    validation_file: str | None = None,
    validation_file_path: str | None = None,
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


@wf.workflow
async def payment_validation_finalize_workflow(
    *,
    job_id: str,
    validation_file: str | None = None,
    validation_file_path: str | None = None,
    process_date_iso: str,
) -> None:
    logger.info("payment_validation_finalize workflow started job_id=%s", job_id)
    await payment_validation_finalize_step(
        job_id=job_id,
        validation_file=validation_file,
        validation_file_path=validation_file_path,
        process_date_iso=process_date_iso,
    )
