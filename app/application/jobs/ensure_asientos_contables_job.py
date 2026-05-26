"""Job: ensure carpetas asientos contables en SharePoint."""

from __future__ import annotations

import logging
from time import perf_counter
from typing import Any

from app.application.job_store_factory import get_job_store
from app.application.use_cases.ensure_asientos_contables_folders import (
    ensure_asientos_contables_folders,
)

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


async def _set_job(job_id: str, updates: dict[str, Any]) -> None:
    await get_job_store().update_job(job_id, updates)


async def execute_ensure_asientos_contables_job(job_id: str, graph: Any) -> None:
    await _set_job(
        job_id,
        {
            "type": "ensure_asientos_contables",
            "status": "running",
            "started_at": _utc_now_iso(),
            "updated_at": _utc_now_iso(),
        },
    )
    logger.info("job %s: ensure_asientos_contables iniciado", job_id)
    started_ts = perf_counter()
    try:
        result = await ensure_asientos_contables_folders(graph)
        elapsed_ms = round((perf_counter() - started_ts) * 1000, 2)
        await _set_job(
            job_id,
            {
                "status": "completed",
                "finished_at": _utc_now_iso(),
                "updated_at": _utc_now_iso(),
                "elapsed_ms": elapsed_ms,
                "result": {
                    "status": "ok",
                    "message": "Ejecutado con éxito",
                    "clients_base_path": result.clients_base_path,
                    "clients_scanned": result.clients_scanned,
                    "credit_folders_scanned": result.credit_folders_scanned,
                    "folders_created": result.folders_created,
                    "folders_already_present": result.folders_already_present,
                    "folders_failed": len(result.errors or []),
                    "subfolder_names": list(result.subfolder_names),
                    "errors": result.errors,
                },
                "error": None,
            },
        )
        logger.info("job %s: ensure_asientos_contables completado", job_id)
    except Exception as exc:
        await _set_job(
            job_id,
            {
                "status": "failed",
                "finished_at": _utc_now_iso(),
                "updated_at": _utc_now_iso(),
                "result": None,
                "error": str(exc),
            },
        )
        logger.exception("job %s: ensure_asientos_contables falló: %s", job_id, exc)
