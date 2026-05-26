"""
Fallback cuando Vercel Workflows encola el run pero el worker no ejecuta el step.

Tras ``start()``, si el job sigue en ``queued`` tras un breve delay, ejecuta la misma
lógica del step en el servicio API (BackgroundTasks), igual que Render.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Awaitable, Callable
from typing import Any

from app.application.job_store_factory import get_job_store

logger = logging.getLogger(__name__)

_DEFAULT_DELAY_SECONDS = 12.0
_DEFAULT_POLL_INTERVAL_SECONDS = 2.0


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


async def run_job_if_still_queued(
    job_id: str,
    *,
    execute: Callable[[], Awaitable[None]],
    label: str,
    delay_seconds: float | None = None,
) -> None:
    """
    Espera y, si el job no avanzó de ``queued``, ejecuta ``execute`` en el servicio API.
    """
    delay = delay_seconds if delay_seconds is not None else workflow_api_fallback_delay_seconds()
    await asyncio.sleep(delay)

    store = get_job_store()
    job = await store.get_job(job_id)
    if job is None:
        logger.warning("workflow_api_fallback skip job_id=%s label=%s (job missing)", job_id, label)
        return

    status = job.get("status")
    if status != "queued":
        print(
            f"WORKFLOW_API_FALLBACK_SKIP job_id={job_id} label={label} status={status}",
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
