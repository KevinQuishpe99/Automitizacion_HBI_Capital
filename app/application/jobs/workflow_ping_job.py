"""Job mínimo para diagnosticar ejecución de Vercel Workflows (sin Graph/SharePoint)."""

from __future__ import annotations

import logging
import os

from app.application.job_runner_settings import job_runner_backend, vercel_workflows_enabled
from app.application.job_manager import JobManager
from app.application.job_store_factory import get_job_store
from app.application.jobs.job_run_guard import JobExecutionSkipped, begin_job_execution
from app.application.job_store_settings import has_blob_token, job_store_backend
from app.application.jobs.workflow_ping_markers import write_marker

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _log_worker_job_store_context(job_id: str) -> None:
    store = get_job_store()
    print(
        "WORKFLOW_PING_STORE_CONTEXT "
        f"job_id={job_id} "
        f"JOB_STORE_BACKEND={job_store_backend() or '(auto)'} "
        f"JOB_RUNNER_BACKEND={job_runner_backend()} "
        f"VERCEL_WORKFLOWS_ENABLED={vercel_workflows_enabled()} "
        f"has_BLOB_READ_WRITE_TOKEN={bool(has_blob_token())} "
        f"has_BLOB_STORE_ID={bool((os.getenv('BLOB_STORE_ID') or '').strip())} "
        f"store_class={type(store).__name__}",
        flush=True,
    )


async def execute_workflow_ping_job(job_id: str) -> None:
    """
    Ejecutado dentro de ``@wf.step`` (side effects durables en el worker).

    queued → running → completed; en error → failed + marker failed.
    """
    print(f"WORKFLOW_PING_EXECUTE_ENTER job_id={job_id}", flush=True)
    _log_worker_job_store_context(job_id)

    await write_marker(job_id, "entered")

    store = get_job_store()
    jm = JobManager()
    try:
        print(f"WORKFLOW_PING_SET_RUNNING job_id={job_id}", flush=True)
        try:
            await begin_job_execution(
                jm, job_id, extra_updates={"type": "workflow_ping"}
            )
        except JobExecutionSkipped:
            return
        await write_marker(job_id, "running")
        logger.info("workflow_ping updating running job_id=%s store=%s", job_id, type(store).__name__)

        print(f"WORKFLOW_PING_SET_COMPLETED job_id={job_id}", flush=True)
        await store.complete_job(
            job_id,
            {"status": "ok", "message": "workflow ping completed"},
        )
        await write_marker(job_id, "completed")
        logger.info("workflow_ping completed job_id=%s", job_id)
    except Exception as exc:
        error_type = type(exc).__name__
        print(f"WORKFLOW_PING_FAILED job_id={job_id} error_type={error_type}", flush=True)
        logger.exception("workflow_ping failed job_id=%s", job_id)
        try:
            await store.fail_job(
                job_id,
                {"type": error_type, "message": str(exc)[:500]},
            )
            await write_marker(job_id, "failed", {"error_type": error_type})
        except Exception:
            logger.exception("workflow_ping could not persist failed status job_id=%s", job_id)
        raise
