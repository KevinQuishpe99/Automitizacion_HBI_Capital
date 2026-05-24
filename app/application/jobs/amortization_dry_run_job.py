"""
Ejecución del job amortization_dry_run (compartido por BackgroundTasks y Vercel Workflow).

No modifica tablas ni mueve PDFs; solo actualiza JobStore.
"""

from __future__ import annotations

import logging
from time import perf_counter
from typing import Any

from app.application.job_manager import JobManager
from app.application.use_cases.amortization_fill_dry_run import run_amortization_fill_dry_run
from app.domain.exceptions import GraphConfigError

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


async def execute_amortization_dry_run_job(
    job_id: str,
    graph: Any,
    *,
    report_date_iso: str | None,
    merge_manifest_path: str | None,
    historical_file_path: str | None,
) -> None:
    """Marca running → ejecuta dry-run → complete/fail en JobStore."""
    jm = JobManager()
    await jm.set_job(
        job_id,
        {
            "status": "running",
            "started_at": _utc_now_iso(),
            "updated_at": _utc_now_iso(),
        },
    )
    logger.info("job %s: amortization_dry_run iniciado", job_id)
    started = perf_counter()
    try:
        result = await run_amortization_fill_dry_run(
            graph,
            report_date_iso=report_date_iso,
            merge_manifest_path=merge_manifest_path,
            historical_file_path=historical_file_path,
        )
        elapsed_ms = round((perf_counter() - started) * 1000, 2)
        await jm.set_job(
            job_id,
            {
                "status": "completed",
                "finished_at": _utc_now_iso(),
                "updated_at": _utc_now_iso(),
                "result": {**result, "elapsed_ms": elapsed_ms},
                "error": None,
            },
        )
        logger.info("job %s: amortization_dry_run completado en %.2fms", job_id, elapsed_ms)
    except ValueError as exc:
        msg = str(exc)
        code = msg.split("|", 1)[0].strip() if "|" in msg else msg.strip()
        await jm.set_job(
            job_id,
            {
                "status": "failed",
                "finished_at": _utc_now_iso(),
                "updated_at": _utc_now_iso(),
                "result": None,
                "error": {
                    "type": "ValueError",
                    "message": msg,
                    "error_code": code,
                },
            },
        )
        logger.warning("job %s: amortization_dry_run falló (validación): %s", job_id, msg)
    except GraphConfigError as exc:
        await jm.set_job(
            job_id,
            {
                "status": "failed",
                "finished_at": _utc_now_iso(),
                "updated_at": _utc_now_iso(),
                "result": None,
                "error": {
                    "type": "GraphConfigError",
                    "message": str(exc),
                    "error_code": "graph_config_error",
                },
            },
        )
        logger.error("job %s: amortization_dry_run config: %s", job_id, exc)
    except Exception as exc:
        await jm.set_job(
            job_id,
            {
                "status": "failed",
                "finished_at": _utc_now_iso(),
                "updated_at": _utc_now_iso(),
                "result": None,
                "error": {"type": type(exc).__name__, "message": str(exc)},
            },
        )
        logger.exception("job %s: amortization_dry_run falló: %s", job_id, exc)
