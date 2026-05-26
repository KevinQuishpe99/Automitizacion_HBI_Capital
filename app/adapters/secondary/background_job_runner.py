from __future__ import annotations

from typing import Any

from fastapi import BackgroundTasks

from app.application.jobs.amortization_apply_job import execute_amortization_apply_job
from app.application.jobs.amortization_dry_run_job import execute_amortization_dry_run_job
from app.application.jobs.workflow_ping_job import execute_workflow_ping_job


class BackgroundJobRunner:
    """Render/local: FastAPI BackgroundTasks (comportamiento histórico)."""

    async def enqueue_amortization_dry_run(
        self,
        *,
        job_id: str,
        graph: Any,
        report_date_iso: str | None,
        merge_manifest_path: str | None,
        historical_file_path: str | None,
        background_tasks: BackgroundTasks | None = None,
    ) -> None:
        if background_tasks is None:
            raise RuntimeError("BackgroundTasks es obligatorio con JOB_RUNNER_BACKEND=background")
        background_tasks.add_task(
            execute_amortization_dry_run_job,
            job_id,
            graph,
            report_date_iso=report_date_iso,
            merge_manifest_path=merge_manifest_path,
            historical_file_path=historical_file_path,
        )

    async def enqueue_amortization_apply(
        self,
        *,
        job_id: str,
        graph: Any,
        report_date_iso: str | None,
        merge_manifest_path: str | None,
        historical_file_path: str | None,
        background_tasks: BackgroundTasks | None = None,
    ) -> None:
        if background_tasks is None:
            raise RuntimeError("BackgroundTasks es obligatorio con JOB_RUNNER_BACKEND=background")
        background_tasks.add_task(
            execute_amortization_apply_job,
            job_id,
            graph,
            report_date_iso=report_date_iso,
            merge_manifest_path=merge_manifest_path,
            historical_file_path=historical_file_path,
        )

    async def enqueue_workflow_ping(
        self,
        *,
        job_id: str,
        background_tasks: BackgroundTasks | None = None,
    ) -> None:
        if background_tasks is None:
            raise RuntimeError("BackgroundTasks es obligatorio con JOB_RUNNER_BACKEND=background")
        background_tasks.add_task(execute_workflow_ping_job, job_id)
