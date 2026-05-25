from __future__ import annotations

import logging
from typing import Any

from fastapi import BackgroundTasks

from app.application.job_manager import JobManager
from app.application.job_runner_settings import (
    workflow_amortization_dry_run_name,
    workflow_ping_name,
)

logger = logging.getLogger(__name__)


class VercelWorkflowJobRunner:
    """Vercel Pro: encola jobs vía ``vercel.workflow.start``."""

    async def _start_workflow(
        self,
        *,
        workflow_fn: Any,
        job_id: str,
        workflow_name: str,
        kwargs: dict[str, Any],
    ) -> None:
        try:
            from vercel.workflow import start
        except ImportError as exc:
            raise RuntimeError(
                "JOB_RUNNER_BACKEND=vercel_workflow requiere el paquete 'vercel' "
                "(pip install vercel>=0.5.2)"
            ) from exc

        logger.info(
            "workflow.start before job_id=%s workflow_name=%s",
            job_id,
            workflow_name,
        )
        run = await start(workflow_fn, job_id=job_id, **kwargs)
        logger.info(
            "workflow.start after job_id=%s workflow_name=%s workflow_run_id=%s",
            job_id,
            workflow_name,
            run.run_id,
        )
        jm = JobManager()
        await jm.set_job(
            job_id,
            {
                "workflow_run_id": run.run_id,
                "workflow_name": workflow_name,
                "updated_at": _utc_now_iso(),
            },
        )

    async def enqueue_workflow_ping(self, *, job_id: str) -> None:
        from app.workflows.workflow_ping_workflow import workflow_ping_workflow

        print(
            f"WORKFLOW_START_PING job_id={job_id} workflow={workflow_ping_name()}",
            flush=True,
        )
        await self._start_workflow(
            workflow_fn=workflow_ping_workflow,
            job_id=job_id,
            workflow_name=workflow_ping_name(),
            kwargs={},
        )

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
        from app.workflows.amortization_dry_run_workflow import amortization_dry_run_workflow

        await self._start_workflow(
            workflow_fn=amortization_dry_run_workflow,
            job_id=job_id,
            workflow_name=workflow_amortization_dry_run_name(),
            kwargs={
                "report_date_iso": report_date_iso,
                "merge_manifest_path": merge_manifest_path,
                "historical_file_path": historical_file_path,
            },
        )


def _utc_now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
