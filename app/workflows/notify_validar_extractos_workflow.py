from __future__ import annotations

import logging

from app.application.jobs.graph_workflow_context import init_graph_for_job
from app.application.jobs.notify_validar_extractos_job import execute_notify_validar_extractos_job
from app.workflows.wf import wf

logger = logging.getLogger(__name__)


@wf.step
async def notify_validar_extractos_step(
    *,
    job_id: str,
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


@wf.workflow
async def notify_validar_extractos_workflow(
    *,
    job_id: str,
    historical_file_path: str | None = None,
    to_override: str | None = None,
    cc_override: str | None = None,
) -> None:
    logger.info("notify_validar_extractos workflow started job_id=%s", job_id)
    await notify_validar_extractos_step(
        job_id=job_id,
        historical_file_path=historical_file_path,
        to_override=to_override,
        cc_override=cc_override,
    )
