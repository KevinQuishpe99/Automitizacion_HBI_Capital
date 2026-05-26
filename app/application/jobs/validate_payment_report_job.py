"""Job: validación masiva del Excel de pagos en SharePoint."""

from __future__ import annotations

import logging
from time import perf_counter
from typing import Any

from app.application.job_manager import JobManager
from app.application.job_store_factory import get_job_store
from app.application.jobs.job_run_guard import JobExecutionSkipped, begin_job_execution
from app.application.use_cases.validate_payment_report import validate_payment_report_and_replace_excel

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


async def _set_job(job_id: str, updates: dict[str, Any]) -> None:
    await get_job_store().update_job(job_id, updates)


async def execute_validate_payment_report_job(job_id: str, graph: Any) -> None:
    jm = JobManager()
    try:
        await begin_job_execution(jm, job_id)
    except JobExecutionSkipped:
        return
    logger.info("job %s: validate_payment_report iniciado", job_id)
    started_ts = perf_counter()
    try:
        summary = await validate_payment_report_and_replace_excel(graph)
        elapsed_ms = round((perf_counter() - started_ts) * 1000, 2)
        await _set_job(
            job_id,
            {
                "status": "completed",
                "finished_at": _utc_now_iso(),
                "updated_at": _utc_now_iso(),
                "result": {
                    "status": "ok",
                    "message": "Ejecutado con éxito",
                    "reaction_time_ms": elapsed_ms,
                    "processed_rows": summary.processed_rows,
                    "ok_count": summary.ok_count,
                    "no_count": summary.no_count,
                    "error_count": summary.error_count,
                    "errors": summary.errors,
                },
                "error": None,
            },
        )
        logger.info("job %s: validate_payment_report completado", job_id)
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
        logger.exception("job %s: validate_payment_report falló: %s", job_id, exc)
