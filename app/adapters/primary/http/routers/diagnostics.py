"""Endpoints temporales de diagnóstico (Vercel Workflows)."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.adapters.secondary.background_job_runner import BackgroundJobRunner
from app.application.job_manager import JobManager
from app.application.job_runner_factory import get_job_runner
from app.application.job_runner_settings import (
    job_runner_backend,
    use_vercel_workflow_runner,
    workflow_ping_name,
)
from app.application.job_store_factory import safe_runtime_config
from app.application.job_status_enrichment import enrich_job_for_http_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/diagnostics", tags=["diagnostics"])


def _utc_now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


@router.get("/runtime-config-safe")
async def get_runtime_config_safe() -> dict[str, str | bool]:
    """Metadata de runtime sin secretos (JobStore/JobRunner en servicio API)."""
    return safe_runtime_config()


@router.post("/workflow-ping/queue", status_code=202)
async def queue_workflow_ping(background_tasks: BackgroundTasks) -> dict[str, Any]:
    """
    Encola ``workflow_ping`` para validar que el worker Vercel ejecuta workflows.
    """
    job_id = str(uuid.uuid4())
    runtime = safe_runtime_config()
    store_label = str(runtime["job_store_backend"])
    runner_label = str(runtime["job_runner_backend"])

    logger.info(
        "workflow_ping queue requested job_id=%s job_store_backend=%s job_runner_backend=%s",
        job_id,
        store_label,
        runner_label,
    )

    jm = JobManager()
    await jm.set_job(
        job_id,
        {
            "job_id": job_id,
            "type": "workflow_ping",
            "status": "queued",
            "queued_at": _utc_now_iso(),
            "updated_at": _utc_now_iso(),
        },
    )

    if use_vercel_workflow_runner():
        runner = get_job_runner()
        enqueue = getattr(runner, "enqueue_workflow_ping", None)
        if enqueue is None:
            raise HTTPException(
                status_code=500,
                detail="JOB_RUNNER_BACKEND=vercel_workflow requiere runner con enqueue_workflow_ping",
            )
        await enqueue(job_id=job_id)
    else:
        bg = BackgroundJobRunner()
        await bg.enqueue_workflow_ping(
            job_id=job_id,
            background_tasks=background_tasks,
        )

    return {"job_id": job_id, "status": "queued"}


@router.get("/workflow-ping/jobs/{job_id}")
async def get_workflow_ping_job(job_id: str) -> dict[str, Any]:
    jm = JobManager()
    raw = await jm.get_job(job_id)
    if raw is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if raw.get("type") != "workflow_ping":
        raise HTTPException(status_code=404, detail="Job is not workflow_ping")
    return enrich_job_for_http_response(raw)
