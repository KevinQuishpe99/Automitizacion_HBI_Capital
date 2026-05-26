"""Endpoints temporales de diagnóstico (Vercel Workflows)."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.adapters.secondary.background_job_runner import BackgroundJobRunner
from app.application.job_manager import JobManager
from app.application.job_runner_factory import get_job_runner
from app.application.job_runner_settings import use_vercel_workflow_runner
from app.application.job_store_factory import get_job_store, safe_runtime_config
from app.application.job_status_enrichment import enrich_job_for_http_response
from app.application.jobs.workflow_ping_markers import list_markers
from app.application.payment_validation_locks import (
    lock_status,
    release_all_payment_validation_locks,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/diagnostics", tags=["diagnostics"])

WORKFLOW_PING_TYPE = "workflow_ping"


def _utc_now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _safe_job_metadata(raw: dict[str, Any]) -> dict[str, Any]:
    request = raw.get("request")
    result = raw.get("result")
    error = raw.get("error")
    return {
        "job_id": raw.get("job_id"),
        "type": raw.get("type"),
        "status": raw.get("status"),
        "queued_at": raw.get("queued_at"),
        "updated_at": raw.get("updated_at"),
        "started_at": raw.get("started_at"),
        "finished_at": raw.get("finished_at"),
        "workflow_run_id": raw.get("workflow_run_id"),
        "workflow_name": raw.get("workflow_name"),
        "request_keys": list(request.keys()) if isinstance(request, dict) else None,
        "result_keys": list(result.keys()) if isinstance(result, dict) else None,
        "error_type": error.get("type") if isinstance(error, dict) else None,
        "error_code": error.get("error_code") if isinstance(error, dict) else None,
        "meta_source": "vercel_blob",
    }


@router.get("/payment-validation/locks")
async def get_payment_validation_locks() -> dict[str, bool | str]:
    """Locks generate/finalize en Blob (útil si Render y Vercel comparten store)."""
    return await lock_status()


@router.post("/payment-validation/locks/release", status_code=200)
async def post_release_payment_validation_locks() -> dict[str, bool | str]:
    """
    Libera locks generate/finalize atascados (p. ej. tras pruebas cruzadas Render+Vercel).
    Solo diagnóstico operativo.
    """
    released = await release_all_payment_validation_locks()
    logger.warning("payment_validation locks released via diagnostics")
    return {"released": True, "locks": released}


@router.get("/runtime-config-safe")
async def get_runtime_config_safe() -> dict[str, str | bool]:
    """Metadata de runtime sin secretos (JobStore/JobRunner en servicio API)."""
    return safe_runtime_config()


@router.get("/jobs/{job_id}/raw-safe")
async def get_job_raw_safe(job_id: str) -> dict[str, Any]:
    store = get_job_store()
    raw = await store.get_job(job_id)
    if raw is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return _safe_job_metadata(raw)


@router.post("/workflow-ping/queue", status_code=202)
async def queue_workflow_ping(background_tasks: BackgroundTasks) -> dict[str, Any]:
    """
    Encola ``workflow_ping`` para validar que el worker Vercel ejecuta workflows.
    """
    job_id = str(uuid.uuid4())
    runtime = safe_runtime_config()
    store_label = str(runtime["job_store_backend"])
    runner_label = str(runtime["job_runner_backend"])

    print(f"WORKFLOW_PING_QUEUE_CREATED job_id={job_id}", flush=True)
    logger.info(
        "workflow_ping queue requested job_id=%s job_store_backend=%s job_runner_backend=%s",
        job_id,
        store_label,
        runner_label,
    )

    store = get_job_store()
    record = {
        "job_id": job_id,
        "type": WORKFLOW_PING_TYPE,
        "status": "queued",
        "queued_at": _utc_now_iso(),
        "updated_at": _utc_now_iso(),
    }
    print(f"WORKFLOW_PING_QUEUE_WRITE type={record['type']} status={record['status']}", flush=True)
    await store.create_job(job_id, record)

    readback = await store.get_job(job_id)
    readback_type = (readback or {}).get("type")
    readback_status = (readback or {}).get("status")
    print(
        f"WORKFLOW_PING_QUEUE_READBACK job_id={job_id} type={readback_type} status={readback_status}",
        flush=True,
    )
    if readback_type != WORKFLOW_PING_TYPE:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "workflow_ping_queue_readback_type_mismatch",
                "job_id": job_id,
                "expected_type": WORKFLOW_PING_TYPE,
                "actual_type": readback_type,
                "actual_status": readback_status,
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
        await enqueue(job_id=job_id, background_tasks=background_tasks)
    else:
        bg = BackgroundJobRunner()
        await bg.enqueue_workflow_ping(
            job_id=job_id,
            background_tasks=background_tasks,
        )

    return {
        "job_id": job_id,
        "status": "queued",
        "type": readback_type,
        "readback_status": readback_status,
    }


@router.get("/workflow-ping/jobs/{job_id}")
async def get_workflow_ping_job(job_id: str) -> dict[str, Any]:
    store = get_job_store()
    raw = await store.get_job(job_id)
    if raw is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if raw.get("type") != WORKFLOW_PING_TYPE:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "Job is not workflow_ping",
                "job_id": job_id,
                "actual_type": raw.get("type"),
                "actual_status": raw.get("status"),
                "workflow_name": raw.get("workflow_name"),
                "workflow_run_id": raw.get("workflow_run_id"),
                "meta_source": "vercel_blob",
            },
        )
    return enrich_job_for_http_response(raw)


@router.get("/workflow-ping/jobs/{job_id}/markers")
async def get_workflow_ping_markers(job_id: str) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "markers": await list_markers(job_id),
        "meta_source": "vercel_blob",
    }
