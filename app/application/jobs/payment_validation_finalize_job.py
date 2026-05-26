"""Job: finalize payment validation flow."""

from __future__ import annotations

import logging
from datetime import date
from time import perf_counter
from typing import Any

from app.application.job_manager import JobManager
from app.application.jobs.job_run_guard import (
    begin_job_execution,
    run_job_body,
    run_with_timeout,
)
from app.application.use_cases.payment_validation_finalize import finalize_payment_validation

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


async def execute_payment_validation_finalize_job(
    job_id: str,
    graph: Any,
    *,
    validation_file: str | None,
    validation_file_path: str | None,
    process_date_iso: str,
) -> None:
    jm = JobManager()
    process_date = date.fromisoformat(process_date_iso)

    async def _run() -> None:
        await begin_job_execution(jm, job_id)
        logger.info("job %s: finalize_payment_validation iniciado", job_id)
        started = perf_counter()
        result = await run_with_timeout(
            finalize_payment_validation(
                graph,
                validation_file=validation_file,
                validation_file_path=validation_file_path,
                process_date=process_date,
            ),
            job_label="finalize",
            job_id=job_id,
        )
        elapsed_ms = round((perf_counter() - started) * 1000, 2)
        await jm.set_job(
            job_id,
            {
                "status": "completed",
                "finished_at": _utc_now_iso(),
                "updated_at": _utc_now_iso(),
                "result": {**result, "elapsed_ms": elapsed_ms},
            },
        )
        logger.info("job %s: completado en %.2fms", job_id, elapsed_ms)

    await run_job_body(
        jm,
        job_id,
        job_label="finalize",
        finish_lock=jm.finish_finalize,
        execute=_run,
    )
