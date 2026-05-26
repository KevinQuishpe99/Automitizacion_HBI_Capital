"""Job: correo notify validar extractos."""

from __future__ import annotations

import logging
from time import perf_counter
from typing import Any

from app.application.job_store_factory import get_job_store
from app.application.use_cases.send_validar_extractos_notification import (
    send_validar_extractos_notification_email,
)
from app.models import NotifyValidarExtractosRequest

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


async def _set_job(job_id: str, updates: dict[str, Any]) -> None:
    await get_job_store().update_job(job_id, updates)


async def execute_notify_validar_extractos_job(
    job_id: str,
    graph: Any,
    *,
    historical_file_path: str | None = None,
    to_override: str | None = None,
    cc_override: str | None = None,
) -> None:
    payload = NotifyValidarExtractosRequest(
        historical_file_path=historical_file_path,
        to=to_override,
        cc=cc_override,
    )
    await _set_job(
        job_id,
        {
            "type": "notify_validar_extractos",
            "status": "running",
            "started_at": _utc_now_iso(),
            "updated_at": _utc_now_iso(),
        },
    )
    logger.info("job %s: notify_validar_extractos iniciado", job_id)
    started_ts = perf_counter()
    try:
        result = await send_validar_extractos_notification_email(
            graph,
            historical_file_path=payload.historical_file_path,
            to_override=payload.to,
            cc_override=payload.cc,
        )
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
                    "report_date": result.report_date,
                    "historical_file_path": result.historical_file_path,
                    "historical_file_source": result.historical_file_source,
                    "historico_excel_path": result.historico_excel_path,
                    "rows_included": result.rows_included,
                    "subject": result.subject,
                    "attachments_count": result.attachments_count,
                    "email_pdf_path": result.email_pdf_path,
                    "email_pdf_error": result.email_pdf_error,
                    "graph_sendmail_http_status": result.graph_sendmail_http_status,
                    "mail_sender": result.mail_sender,
                    "mail_to": result.mail_to,
                    "merge_control_updated": result.merge_control_updated,
                    "merge_control_file_path": result.merge_control_file_path,
                    "merge_control_status": result.merge_control_status,
                    "merge_control_warning": result.merge_control_warning,
                    "merge_control_error_code": result.merge_control_error_code,
                },
                "error": None,
            },
        )
        logger.info("job %s: notify_validar_extractos completado", job_id)
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
        logger.exception("job %s: notify_validar_extractos falló: %s", job_id, exc)
