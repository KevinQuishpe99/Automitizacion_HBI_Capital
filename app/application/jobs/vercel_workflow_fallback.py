"""
Fallback cuando Vercel Workflows encola el run pero el worker no ejecuta el step.

Tras ``start()``, si el job no avanza en Blob, la API ejecuta el mismo job (como Render).
En Vercel se programa con ``asyncio.create_task`` (BackgroundTasks no es fiable tras el 202).
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any

from app.application.job_store_factory import get_job_store
from app.application.job_store_settings import is_vercel_runtime

logger = logging.getLogger(__name__)

_DEFAULT_DELAY_SECONDS = 12.0
_DEFAULT_POLL_INTERVAL_SECONDS = 2.0
_DEFAULT_WORKFLOW_WAIT_SECONDS = 20.0
_DEFAULT_DISPATCH_TAKEOVER_SECONDS = 20.0
_TERMINAL_STATUSES = frozenset({"completed", "failed"})
_EXECUTION_PHASE_DISPATCHED = "workflow_dispatched"
_EXECUTION_PHASE_EXECUTING = "executing"

_fallback_runner_lock = asyncio.Lock()
_fallback_runner_job_ids: set[str] = set()


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
        return max(0.5, float(raw))
    except ValueError:
        return _DEFAULT_POLL_INTERVAL_SECONDS


def workflow_api_fallback_workflow_wait_seconds() -> float:
    raw = (os.getenv("VERCEL_WORKFLOW_API_FALLBACK_WORKFLOW_WAIT_SECONDS") or "").strip()
    if not raw:
        return _DEFAULT_WORKFLOW_WAIT_SECONDS
    try:
        return max(0.0, float(raw))
    except ValueError:
        return _DEFAULT_WORKFLOW_WAIT_SECONDS


def workflow_dispatch_takeover_seconds() -> float:
    """Tras ``workflow_dispatched``, la API toma el job si el worker no pasa a ``executing``."""
    raw = (os.getenv("VERCEL_WORKFLOW_DISPATCH_TAKEOVER_SECONDS") or "").strip()
    if not raw:
        return _DEFAULT_DISPATCH_TAKEOVER_SECONDS
    try:
        return max(5.0, float(raw))
    except ValueError:
        return _DEFAULT_DISPATCH_TAKEOVER_SECONDS


def workflow_stale_running_seconds() -> float:
    """Tras este tiempo en ``running``/``executing`` sin terminal, el fallback marca ``failed``."""
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


def _should_run_fallback_for_running(job: dict[str, Any], *, stale_running_s: float) -> str:
    """
    ``run`` → ejecutar fallback en API; ``skip`` → otro runner activo; ``fail`` → estancado.
    """
    status = str(job.get("status") or "")
    if status in _TERMINAL_STATUSES:
        return "skip"
    if status != "running":
        return "run"

    phase = str(job.get("execution_phase") or "")
    elapsed = _running_stale_seconds(job)

    if phase == _EXECUTION_PHASE_DISPATCHED:
        takeover = workflow_dispatch_takeover_seconds()
        if elapsed is not None and elapsed >= takeover:
            return "run"
        return "skip"

    if elapsed is not None and elapsed >= stale_running_s:
        return "fail"
    return "skip"


async def _poll_until_fallback_or_skip(
    job_id: str,
    *,
    label: str,
    store: Any,
    stale_running_s: float,
) -> str:
    """
    Devuelve ``skip``, ``run`` o ``fail`` según el estado observado en Blob.
    """
    wait_s = workflow_api_fallback_workflow_wait_seconds()
    if wait_s <= 0:
        return "run"

    interval = workflow_api_fallback_poll_interval_seconds()
    deadline = datetime.now(timezone.utc).timestamp() + wait_s

    while datetime.now(timezone.utc).timestamp() < deadline:
        job = await store.get_job(job_id)
        if job is None:
            await asyncio.sleep(interval)
            continue

        status = str(job.get("status") or "")
        if status in _TERMINAL_STATUSES:
            print(
                f"WORKFLOW_API_FALLBACK_SKIP job_id={job_id} label={label} status={status}",
                flush=True,
            )
            return "skip"

        if status == "queued":
            await asyncio.sleep(interval)
            continue

        action = _should_run_fallback_for_running(job, stale_running_s=stale_running_s)
        if action == "run":
            return "run"
        if action == "fail":
            elapsed = _running_stale_seconds(job) or stale_running_s
            await _mark_stale_running_failed(job_id, label=label, stale_s=elapsed)
            return "skip"
        await asyncio.sleep(interval)

    job = await store.get_job(job_id)
    if job is None:
        return "run"
    status = str(job.get("status") or "")
    if status in _TERMINAL_STATUSES:
        return "skip"
    if status == "queued":
        return "run"
    action = _should_run_fallback_for_running(job, stale_running_s=stale_running_s)
    if action == "fail":
        elapsed = _running_stale_seconds(job) or stale_running_s
        await _mark_stale_running_failed(job_id, label=label, stale_s=elapsed)
        return "skip"
    if action == "run":
        return "run"
    return "skip"


async def _try_claim_fallback_runner(job_id: str) -> bool:
    async with _fallback_runner_lock:
        if job_id in _fallback_runner_job_ids:
            return False
        _fallback_runner_job_ids.add(job_id)
        return True


async def _release_fallback_runner(job_id: str) -> None:
    async with _fallback_runner_lock:
        _fallback_runner_job_ids.discard(job_id)


async def run_job_if_still_queued(
    job_id: str,
    *,
    execute: Callable[[], Awaitable[None]],
    label: str,
    delay_seconds: float | None = None,
) -> None:
    """
    Espera y, si el job no terminó en Blob, ejecuta ``execute`` en la API o marca failed.
    """
    if not await _try_claim_fallback_runner(job_id):
        logger.info("workflow_api_fallback duplicate runner skipped job_id=%s", job_id)
        return

    try:
        delay = (
            delay_seconds
            if delay_seconds is not None
            else workflow_api_fallback_delay_seconds()
        )
        stale_running_s = workflow_stale_running_seconds()
        await asyncio.sleep(delay)

        store = get_job_store()
        job = await store.get_job(job_id)
        if job is None:
            logger.warning(
                "workflow_api_fallback skip job_id=%s label=%s (job missing)", job_id, label
            )
            return

        status = str(job.get("status") or "")
        if status in _TERMINAL_STATUSES:
            print(
                f"WORKFLOW_API_FALLBACK_SKIP job_id={job_id} label={label} status={status}",
                flush=True,
            )
            return

        if status == "running":
            action = _should_run_fallback_for_running(job, stale_running_s=stale_running_s)
            if action == "skip":
                print(
                    f"WORKFLOW_API_FALLBACK_SKIP job_id={job_id} label={label} "
                    f"status=running phase={job.get('execution_phase')}",
                    flush=True,
                )
                return
            if action == "fail":
                elapsed = _running_stale_seconds(job) or stale_running_s
                await _mark_stale_running_failed(job_id, label=label, stale_s=elapsed)
                return
        elif status != "queued":
            print(
                f"WORKFLOW_API_FALLBACK_SKIP job_id={job_id} label={label} status={status}",
                flush=True,
            )
            return

        if job.get("workflow_run_id"):
            poll_action = await _poll_until_fallback_or_skip(
                job_id, label=label, store=store, stale_running_s=stale_running_s
            )
            if poll_action == "skip":
                return

        print(
            f"WORKFLOW_API_FALLBACK_RUN job_id={job_id} label={label} delay_s={delay}",
            flush=True,
        )
        logger.warning(
            "workflow_api_fallback executing inline job_id=%s label=%s",
            job_id,
            label,
        )
        try:
            await execute()
        except Exception:
            logger.exception("workflow_api_fallback failed job_id=%s label=%s", job_id, label)
            raise
    finally:
        await _release_fallback_runner(job_id)


def schedule_workflow_api_fallback(
    background_tasks: Any,
    *,
    job_id: str,
    execute: Callable[[], Awaitable[None]],
    label: str,
) -> None:
    """Programa fallback: ``create_task`` en Vercel; BackgroundTasks en Render/local."""
    if not workflow_api_fallback_enabled():
        return

    coro = run_job_if_still_queued(job_id, execute=execute, label=label)

    if is_vercel_runtime():
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(coro)
            logger.info("workflow_api_fallback scheduled via create_task job_id=%s", job_id)
        except RuntimeError:
            logger.warning(
                "workflow_api_fallback: sin event loop; job_id=%s label=%s", job_id, label
            )
        return

    if background_tasks is None:
        return
    background_tasks.add_task(run_job_if_still_queued, job_id, execute=execute, label=label)
