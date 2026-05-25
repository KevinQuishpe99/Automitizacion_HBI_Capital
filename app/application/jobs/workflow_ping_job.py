"""Job mínimo para diagnosticar ejecución de Vercel Workflows (sin Graph/SharePoint)."""

from __future__ import annotations

import logging

from app.application.job_manager import JobManager

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


async def execute_workflow_ping_job(job_id: str) -> None:
    """queued → running → completed con result simple."""
    logger.info("workflow_ping job execute starting job_id=%s (before running)", job_id)
    jm = JobManager()
    await jm.set_job(
        job_id,
        {
            "status": "running",
            "started_at": _utc_now_iso(),
            "updated_at": _utc_now_iso(),
        },
    )
    logger.info("workflow_ping updating running job_id=%s", job_id)
    await jm.store.complete_job(
        job_id,
        {"status": "ok", "message": "workflow ping completed"},
    )
    logger.info("workflow_ping completed job_id=%s", job_id)
