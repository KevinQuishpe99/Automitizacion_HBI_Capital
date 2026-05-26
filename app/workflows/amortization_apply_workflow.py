"""
Workflow durable: amortization apply (escritura real en SharePoint).

Registrado en ``app/workflows/index.py`` (worker Vercel).
"""

from __future__ import annotations

import logging

from app.application.jobs.amortization_apply_job import execute_amortization_apply_job
from app.workflows.wf import wf

logger = logging.getLogger(__name__)

print("AMORTIZATION_APPLY_IMPORTED", flush=True)


@wf.step
async def amortization_apply_step(
    *,
    job_id: str,
    report_date_iso: str | None = None,
    merge_manifest_path: str | None = None,
    historical_file_path: str | None = None,
) -> None:
    print(f"AMORTIZATION_APPLY_STEP_ENTER job_id={job_id}", flush=True)
    from app.adapters.primary.http.deps import get_graph_client, init_graph_client
    from app.adapters.secondary.ms_graph_client import MsGraphClient

    init_graph_client(MsGraphClient())
    graph = get_graph_client()
    await execute_amortization_apply_job(
        job_id,
        graph,
        report_date_iso=report_date_iso,
        merge_manifest_path=merge_manifest_path,
        historical_file_path=historical_file_path,
    )


@wf.workflow
async def amortization_apply_workflow(
    *,
    job_id: str,
    report_date_iso: str | None = None,
    merge_manifest_path: str | None = None,
    historical_file_path: str | None = None,
) -> None:
    print(f"AMORTIZATION_APPLY_WORKFLOW_STARTED job_id={job_id}", flush=True)
    logger.info("amortization_apply workflow started job_id=%s", job_id)
    await amortization_apply_step(
        job_id=job_id,
        report_date_iso=report_date_iso,
        merge_manifest_path=merge_manifest_path,
        historical_file_path=historical_file_path,
    )
