"""
Fallback cuando Vercel Workflows encola el run pero el worker no ejecuta el step.

Tras ``start()``, si el job sigue en ``queued`` o en ``running`` estancado, ejecuta o marca
failed en el servicio API (BackgroundTasks), igual que Render.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any

from app.application.job_store_factory import get_job_store

logger = logging.getLogger(__name__)

_DEFAULT_DELAY_SECONDS = 12.0
_DEFAULT_POLL_INTERVAL_SECONDS = 2.0
_DEFAULT_WORKFLOW_WAIT_SECONDS = 30.0
_TERMINAL_STATUSES = frozenset({"completed", "failed"})


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def workflow_api_fallback_enabled() -> bool:
    """Por defecto activo en Vercel; desactivar con VERCEL_WORKFLOW_API_FALLBACK=false."""
    raw = (os.getenv("VERCEL_WORKFLOW_API_FALLBACK") or "").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    vercel = (os.getenv("VERCEL") or "").strip() == "1"
    return vercel or raw in ("1", "true", "yes", "on")


def workflow_api_fallback_delay_seconds() -> float:
    raw = (os.getenv("VERCEL_WORKFLOW_API_FALLBACK_DELAY_SECONDS") or "").strip()
    if not raw:
        return _DEFAULT_DELAY_SECONDS
    try:
        return max(3.0, float(raw))
    except ValueError:
        return _DEFAULT_DELAY_SECONDS


def workflow_api_fallback_poll_interval_seconds() -> float:
    raw = (os.getenv("VERCEL_WORKFLOW_API_FALLBACK_POLL_SECONDS") or "").strip()
    if not raw:
        return _DEFAULT_POLL_INTERVAL_SECONDS
    try:
        return max(1.0, float(raw))
    except ValueError:
        return _DEFAULT_POLL_INTERVAL_SECONDS


def workflow_api_fallback_workflow_wait_seconds() -> float:
    """Tras el delay inicial, esperar a que el worker pase queued→running si hay workflow_run_id."""
    raw = (os.getenv("VERCEL_WORKFLOW_API_FALLBACK_WORKFLOW_WAIT_SECONDS") or "").strip()
    if not raw:
        return _DEFAULT_WORKFLOW_WAIT_SECONDS
    try:
        return max(0.0, float(raw))
    except ValueError:
        return _DEFAULT_WORKFLOW_WAIT_SECONDS


def workflow_stale_running_seconds() -> float:
    """Tras este tiempo en ``running`` sin terminal, el fallback marca ``failed`` en la API."""
    raw = (os.getenv("VERCEL_WORKFLOW_STALE_RUNNING_SECONDS") or "").strip()
    if raw:
        try:
            return max(60.0, float(raw))
        except ValueError:
            pass
    from app.application.jobs.job_run_guard import job_step_timeout_seconds

    return job_step_timeout_seconds("finalize") + 60.0


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _running_stale_seconds(job: dict[str, Any]) -> float | None:
    started = _parse_iso(job.get("started_at"))
    if started is None:
        return None
    return (datetime.now(timezone.utc) - started).total_seconds()


async def _mark_stale_running_failed(job_id: str, *, label: str, stale_s: float) -> None:
    store = get_job_store()
    await store.update_job(
        job_id,
        {
            "status": "failed",
            "finished_at": _utc_now_iso(),
            "updated_at": _utc_now_iso(),
            "error": {
                "type": "JobStaleRunning",
                "message": (
                    f"El job quedó en running más de {int(stale_s)}s sin completar "
                    f"(worker Vercel no terminó el step {label}). Reintente la operación."
                ),
                "error_code": "job_stuck_running",
            },
        },
    )
    logger.warning(
        "workflow_api_fallback marked stale running as failed job_id=%s label=%s",
        job_id,
        label,
    )


async def _wait_for_workflow_worker_pickup(
    job_id: str,
    *,
    label: str,
    store: Any,
) -> bool:
    """
    True si conviene omitir el fallback (el worker avanzó o el job terminó).
    """
    wait_s = workflow_api_fallback_workflow_wait_seconds()
    if wait_s <= 0:
        return False
    interval = workflow_api_fallback_poll_interval_seconds()
    polls = max(1, int(wait_s / interval))
    for _ in range(polls):
        await asyncio.sleep(interval)
        job = await store.get_job(job_id)
        if job is None:
            return True
        status = str(job.get("status") or "")
        if status in _TERMINAL_STATUSES:
            print(
                f"WORKFLOW_API_FALLBACK_SKIP job_id={job_id} label={label} "
                f"status={status} (workflow finished during wait)",
                flush=True,
            )
            return True
        if status == "running":
            print(
                f"WORKFLOW_API_FALLBACK_SKIP job_id={job_id} label={label} "
                f"status=running (worker picked up)",
                flush=True,
            )
            return True
    return False


async def run_job_if_still_queued(
    job_id: str,
    *,
    execute: Callable[[], Awaitable[None]],
    label: str,
    delay_seconds: float | None = None,
) -> None:
    """
    Espera y, si el job no terminó, ejecuta ``execute`` en el servicio API o marca failed
    si quedó en ``running`` estancado (típico cuando el worker muere tras poner running).
    """
    delay = delay_seconds if delay_seconds is not None else workflow_api_fallback_delay_seconds()
    stale_running_s = workflow_stale_running_seconds()
    await asyncio.sleep(delay)

    store = get_job_store()
    job = await store.get_job(job_id)
    if job is None:
        logger.warning("workflow_api_fallback skip job_id=%s label=%s (job missing)", job_id, label)
        return

    status = str(job.get("status") or "")
    if status in _TERMINAL_STATUSES:
        print(
            f"WORKFLOW_API_FALLBACK_SKIP job_id={job_id} label={label} status={status}",
            flush=True,
        )
        return

    if status == "running":
        elapsed = _running_stale_seconds(job)
        if elapsed is None or elapsed < stale_running_s:
            print(
                f"WORKFLOW_API_FALLBACK_SKIP job_id={job_id} label={label} "
                f"status=running elapsed_s={elapsed}",
                flush=True,
            )
            return
        print(
            f"WORKFLOW_API_FALLBACK_STALE_RUNNING job_id={job_id} label={label} "
            f"elapsed_s={elapsed}",
            flush=True,
        )
        await _mark_stale_running_failed(job_id, label=label, stale_s=elapsed)
        return

    if status != "queued":
        print(
            f"WORKFLOW_API_FALLBACK_SKIP job_id={job_id} label={label} status={status}",
            flush=True,
        )
        return

    if job.get("workflow_run_id"):
        if await _wait_for_workflow_worker_pickup(job_id, label=label, store=store):
            return
        job = await store.get_job(job_id)
        if job is None:
            return
        status = str(job.get("status") or "")
        if status in _TERMINAL_STATUSES or status == "running":
            print(
                f"WORKFLOW_API_FALLBACK_SKIP job_id={job_id} label={label} "
                f"status={status} after workflow wait",
                flush=True,
            )
            return

    print(
        f"WORKFLOW_API_FALLBACK_RUN job_id={job_id} label={label} delay_s={delay}",
        flush=True,
    )
    logger.warning(
        "workflow_api_fallback executing inline job_id=%s label=%s (worker did not advance job)",
        job_id,
        label,
    )
    try:
        await execute()
    except Exception:
        logger.exception("workflow_api_fallback failed job_id=%s label=%s", job_id, label)
        raise


def schedule_workflow_api_fallback(
    background_tasks: Any,
    *,
    job_id: str,
    execute: Callable[[], Awaitable[None]],
    label: str,
) -> None:
    """Programa el fallback vía FastAPI BackgroundTasks (sobrevive al 202 en Vercel API)."""
    if not workflow_api_fallback_enabled():
        return
    if background_tasks is None:
        return
    background_tasks.add_task(run_job_if_still_queued, job_id, execute=execute, label=label)
