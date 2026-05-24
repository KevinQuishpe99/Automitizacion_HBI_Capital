from __future__ import annotations

import logging
from typing import Any

from fastapi import BackgroundTasks

from app.application.job_manager import JobManager
from app.application.job_runner_settings import workflow_amortization_dry_run_name

logger = logging.getLogger(__name__)


class VercelWorkflowJobRunner:
    """Vercel Pro: encola amortization dry-run vía ``vercel.workflow.start``."""

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
        del graph, background_tasks
        try:
            from vercel.workflow import start
        except ImportError as exc:
            raise RuntimeError(
                "JOB_RUNNER_BACKEND=vercel_workflow requiere el paquete 'vercel' "
                "(pip install vercel>=0.5.2)"
            ) from exc

        from app.workflows.amortization_dry_run_workflow import amortization_dry_run_workflow

        run = await start(
            amortization_dry_run_workflow,
            job_id=job_id,
            report_date_iso=report_date_iso,
            merge_manifest_path=merge_manifest_path,
            historical_file_path=historical_file_path,
        )
        jm = JobManager()
        await jm.set_job(
            job_id,
            {
                "workflow_run_id": run.run_id,
                "workflow_name": workflow_amortization_dry_run_name(),
                "updated_at": _utc_now_iso(),
            },
        )
        logger.info(
            "job %s: workflow %s iniciado run_id=%s",
            job_id,
            workflow_amortization_dry_run_name(),
            run.run_id,
        )


def _utc_now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
