"""
Workflow durable mínimo: ping de diagnóstico (sin Graph, SharePoint ni PDFs).

El trabajo real va en ``@wf.step`` (mismo patrón que amortization_dry_run).
"""

from __future__ import annotations

import logging

from app.application.jobs.workflow_ping_job import execute_workflow_ping_job
from app.workflows.wf import wf

logger = logging.getLogger(__name__)

print("WORKFLOW_PING_IMPORTED", flush=True)


@wf.step
async def workflow_ping_step(*, job_id: str) -> None:
    print(f"WORKFLOW_PING_STEP_ENTER job_id={job_id}", flush=True)
    await execute_workflow_ping_job(job_id)


@wf.workflow
async def workflow_ping_workflow(*, job_id: str) -> None:
    print(f"WORKFLOW_PING_STARTED job_id={job_id}", flush=True)
    logger.info("workflow_ping started job_id=%s", job_id)
    await workflow_ping_step(job_id=job_id)
