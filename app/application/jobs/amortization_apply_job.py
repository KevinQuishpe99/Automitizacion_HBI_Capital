"""
Ejecución del job amortization_apply (compartido por BackgroundTasks y Vercel Workflow).

Delega en ``run_amortization_fill_apply`` (preflight, escritura SharePoint, verificación).
"""

from __future__ import annotations

import logging
from time import perf_counter
from typing import Any

from app.application.job_manager import JobManager
from app.application.use_cases.amortization_fill_apply import run_amortization_fill_apply
from app.domain.exceptions import GraphConfigError

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


async def execute_amortization_apply_job(
    job_id: str,
    graph: Any,
    *,
    report_date_iso: str | None,
    merge_manifest_path: str | None,
    historical_file_path: str | None,
) -> None:
    """Marca running → apply → complete/fail en JobStore."""
    print(f"AMORTIZATION_APPLY_SET_RUNNING job_id={job_id}", flush=True)
    jm = JobManager()
    await jm.set_job(
        job_id,
        {
            "type": "amortization_apply",
            "status": "running",
            "started_at": _utc_now_iso(),
            "updated_at": _utc_now_iso(),
        },
    )
    logger.info("job %s: amortization_apply iniciado", job_id)
    started = perf_counter()
    try:
        result = await run_amortization_fill_apply(
            graph,
            report_date_iso=report_date_iso,
            merge_manifest_path=merge_manifest_path,
            historical_file_path=historical_file_path,
        )
        elapsed_ms = round((perf_counter() - started) * 1000, 2)

        # Observabilidad/guardrails: señales sobre si se escribió/subió algo
        summary = result.get("summary") or {}
        tables_uploaded = result.get("tables_uploaded") or []
        tables_summary = result.get("tables_summary") or []

        tables_uploaded_count = len(tables_uploaded)
        tables_skipped_count = sum(
            1
            for ts in tables_summary
            if str(ts.get("upload_status") or "").strip().lower() == "skipped"
        )
        idempotent_skips_count = int(summary.get("skipped_idempotent") or 0)

        summary_total = int(summary.get("total") or 0)
        all_skipped_idempotent = bool(
            summary_total > 0
            and idempotent_skips_count == summary_total
            and tables_uploaded_count == 0
        )

        applied = int(summary.get("applied") or 0)
        adopted = int(summary.get("adopted") or 0)
        apply_wrote_changes = bool((applied + adopted) > 0 or tables_uploaded_count > 0)

        await jm.set_job(
            job_id,
            {
                "status": "completed",
                "finished_at": _utc_now_iso(),
                "updated_at": _utc_now_iso(),
                "result": {
                    **result,
                    "elapsed_ms": elapsed_ms,
                    "tables_uploaded_count": tables_uploaded_count,
                    "tables_skipped_count": tables_skipped_count,
                    "idempotent_skips_count": idempotent_skips_count,
                    "all_skipped_idempotent": all_skipped_idempotent,
                    "apply_wrote_changes": apply_wrote_changes,
                },
                "error": None,
            },
        )
        print(f"AMORTIZATION_APPLY_COMPLETED job_id={job_id}", flush=True)
        logger.info("job %s: amortization_apply completado en %.2fms", job_id, elapsed_ms)
    except ValueError as exc:
        msg = str(exc)
        code = msg.split("|", 1)[0].strip() if "|" in msg else msg.strip()
        print(f"AMORTIZATION_APPLY_FAILED job_id={job_id} error_type=ValueError", flush=True)
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
        logger.warning("job %s: amortization_apply falló (validación): %s", job_id, msg)
    except GraphConfigError as exc:
        print(f"AMORTIZATION_APPLY_FAILED job_id={job_id} error_type=GraphConfigError", flush=True)
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
        logger.error("job %s: amortization_apply config: %s", job_id, exc)
    except Exception as exc:
        print(
            f"AMORTIZATION_APPLY_FAILED job_id={job_id} error_type={type(exc).__name__}",
            flush=True,
        )
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
        logger.exception("job %s: amortization_apply falló: %s", job_id, exc)
