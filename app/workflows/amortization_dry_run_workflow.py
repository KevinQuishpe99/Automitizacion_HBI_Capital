"""
Workflow durable: amortization dry-run (Fase 4).

Registrado en vercel.json → experimentalServices.amortization_dry_run (Services mode).
Requiere JOB_RUNNER_BACKEND=vercel_workflow y VERCEL_WORKFLOWS_ENABLED=true en Vercel.
"""

from __future__ import annotations

from app.application.jobs.amortization_dry_run_job import execute_amortization_dry_run_job
from app.workflows.wf import wf


@wf.step
async def amortization_dry_run_step(
    *,
    job_id: str,
    report_date_iso: str | None = None,
    merge_manifest_path: str | None = None,
    historical_file_path: str | None = None,
) -> None:
    from app.adapters.primary.http.deps import get_graph_client, init_graph_client
    from app.adapters.secondary.ms_graph_client import MsGraphClient

    init_graph_client(MsGraphClient())
    graph = get_graph_client()
    await execute_amortization_dry_run_job(
        job_id,
        graph,
        report_date_iso=report_date_iso,
        merge_manifest_path=merge_manifest_path,
        historical_file_path=historical_file_path,
    )


@wf.workflow
async def amortization_dry_run_workflow(
    *,
    job_id: str,
    report_date_iso: str | None = None,
    merge_manifest_path: str | None = None,
    historical_file_path: str | None = None,
) -> None:
    await amortization_dry_run_step(
        job_id=job_id,
        report_date_iso=report_date_iso,
        merge_manifest_path=merge_manifest_path,
        historical_file_path=historical_file_path,
    )
