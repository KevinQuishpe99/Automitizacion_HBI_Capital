"""Garantías de que un job no quede en ``running`` sin terminal (failed/completed)."""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

_TERMINAL_STATUSES = frozenset({"completed", "failed"})


class JobExecutionSkipped(Exception):
    """Otra instancia ya terminó o está ejecutando este job (workflow + fallback)."""


def _utc_now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def job_step_timeout_seconds(job_label: str) -> float:
    """Timeout por tipo de job (env ``JOB_<LABEL>_TIMEOUT_SECONDS`` o ``JOB_STEP_TIMEOUT_SECONDS``)."""
    specific = (os.getenv(f"JOB_{job_label.upper()}_TIMEOUT_SECONDS") or "").strip()
    raw = specific or (os.getenv("JOB_STEP_TIMEOUT_SECONDS") or "900").strip()
    try:
        return max(30.0, float(raw))
    except ValueError:
        return 900.0


def _job_has_success_payload(job: dict[str, Any]) -> bool:
    if job.get("result"):
        return True
    if job.get("result_summary"):
        return True
    return bool(job.get("result_ref"))


async def begin_job_execution(
    job_manager: Any,
    job_id: str,
    *,
    extra_updates: dict[str, Any] | None = None,
) -> None:
    """
    Pasa ``queued`` → ``running`` solo si nadie más está ejecutando o terminó.

    Evita que workflow y fallback API pisen un ``completed`` con ``running``.
    """
    running_updates: dict[str, Any] = {
        "status": "running",
        "started_at": _utc_now_iso(),
        "updated_at": _utc_now_iso(),
        "execution_phase": "executing",
    }
    if extra_updates:
        running_updates.update(extra_updates)

    job = await job_manager.get_job(job_id)
    if job is None:
        await job_manager.set_job(job_id, running_updates)
        return

    status = str(job.get("status") or "")
    if status in _TERMINAL_STATUSES:
        raise JobExecutionSkipped(f"job already {status}")
    if status == "running":
        phase = str(job.get("execution_phase") or "")
        if phase == "workflow_dispatched":
            running_updates["execution_phase"] = "executing"
            await job_manager.set_job(job_id, running_updates)
            return
        raise JobExecutionSkipped("job already running")
    if status != "queued":
        raise JobExecutionSkipped(f"unexpected status {status}")

    await job_manager.set_job(job_id, running_updates)


async def reconcile_job_terminal(job_manager: Any, job_id: str) -> bool:
    """True si el job ya está terminal o tiene resultado persistido."""
    job = await job_manager.get_job(job_id)
    if not job:
        return False
    if str(job.get("status") or "") in _TERMINAL_STATUSES:
        return True
    if str(job.get("status") or "") == "running" and _job_has_success_payload(job):
        await job_manager.set_job(
            job_id,
            {
                "status": "completed",
                "finished_at": job.get("finished_at") or _utc_now_iso(),
                "updated_at": _utc_now_iso(),
                "error": None,
            },
        )
        logger.warning(
            "job %s: reconciliado a completed (tenía result pero status running)",
            job_id,
        )
        return True
    return False


async def run_with_timeout(
    coro: Awaitable[T],
    *,
    job_label: str,
    job_id: str,
) -> T:
    timeout = job_step_timeout_seconds(job_label)
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError as exc:
        raise TimeoutError(f"{job_label}_timeout|job_id={job_id}|limit_s={int(timeout)}") from exc


async def fail_job_if_still_running(
    job_manager: Any,
    job_id: str,
    *,
    reason: str = "job_aborted_before_terminal_status",
) -> None:
    """Marca ``failed`` si el job sigue en ``running`` (p. ej. proceso serverless cortado)."""
    if await reconcile_job_terminal(job_manager, job_id):
        return
    job = await job_manager.get_job(job_id)
    if job is None or job.get("status") != "running":
        return
    await job_manager.set_job(
        job_id,
        {
            "status": "failed",
            "finished_at": _utc_now_iso(),
            "updated_at": _utc_now_iso(),
            "error": {
                "type": "JobAborted",
                "message": reason,
                "error_code": "job_stuck_running",
            },
        },
    )
    logger.error("job %s: marcado failed (seguía running): %s", job_id, reason)


async def run_job_body(
    job_manager: Any,
    job_id: str,
    *,
    job_label: str,
    finish_lock: Callable[[], Awaitable[None]],
    execute: Callable[[], Awaitable[None]],
) -> None:
    """
    Ejecuta ``execute`` con timeout y asegura estado terminal + liberación de lock.
    ``execute`` debe poner completed/failed; si no, se fuerza failed en ``finally``.
    """
    terminal = False
    try:
        await execute()
        if await reconcile_job_terminal(job_manager, job_id):
            terminal = True
        else:
            job = await job_manager.get_job(job_id)
            if job and job.get("status") in _TERMINAL_STATUSES:
                terminal = True
    except JobExecutionSkipped as exc:
        if await reconcile_job_terminal(job_manager, job_id):
            terminal = True
        else:
            job = await job_manager.get_job(job_id)
            if job and str(job.get("status") or "") == "running":
                terminal = True
                logger.info(
                    "job %s (%s): ejecución duplicada omitida (%s), otro runner activo",
                    job_id,
                    job_label,
                    exc,
                )
            else:
                terminal = True
                logger.info(
                    "job %s (%s): ejecución omitida (%s)",
                    job_id,
                    job_label,
                    exc,
                )
    except Exception as exc:
        if await reconcile_job_terminal(job_manager, job_id):
            terminal = True
            logger.warning(
                "job %s (%s): excepción ignorada, job ya terminal: %s",
                job_id,
                job_label,
                exc,
            )
        else:
            try:
                await job_manager.set_job(
                    job_id,
                    {
                        "status": "failed",
                        "finished_at": _utc_now_iso(),
                        "updated_at": _utc_now_iso(),
                        "error": {
                            "type": type(exc).__name__,
                            "message": str(exc),
                        },
                    },
                )
                terminal = True
            except Exception:
                logger.exception("job %s: no se pudo persistir failed", job_id)
            logger.error(
                "job %s (%s) falló: %s: %s", job_id, job_label, type(exc).__name__, exc
            )
    finally:
        try:
            await finish_lock()
        except Exception:
            logger.exception("job %s: finish_lock falló", job_id)
        if not terminal:
            if await reconcile_job_terminal(job_manager, job_id):
                terminal = True
        if not terminal:
            await fail_job_if_still_running(
                job_manager,
                job_id,
                reason=f"{job_label}_exited_without_terminal_status",
            )
