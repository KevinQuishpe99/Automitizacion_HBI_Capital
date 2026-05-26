"""Job: merge de PDFs composite validado."""

from __future__ import annotations

import logging
from time import perf_counter
from typing import Any

from app.application.job_store_factory import get_job_store
from app.application.use_cases.merge_composite_validado_pdfs import merge_composite_validado_pdfs

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


async def _set_job(job_id: str, updates: dict[str, Any]) -> None:
    await get_job_store().update_job(job_id, updates)


async def execute_merge_composite_validado_pdfs_job(
    job_id: str,
    graph: Any,
    *,
    force_rebuild: bool = False,
) -> None:
    await _set_job(
        job_id,
        {
            "type": "merge_composite_validado_pdfs",
            "status": "running",
            "started_at": _utc_now_iso(),
            "updated_at": _utc_now_iso(),
        },
    )
    logger.info("job %s: merge_composite_validado_pdfs iniciado", job_id)
    started_ts = perf_counter()
    try:
        result = await merge_composite_validado_pdfs(graph, force_rebuild=force_rebuild)
        elapsed_ms = round((perf_counter() - started_ts) * 1000, 2)

        # Guardrails/observabilidad: clasificar outputs por acción (created/reused/skipped)
        outputs_payload: list[dict[str, Any]] = []
        files_created = 0
        files_reused = 0
        files_skipped = result.skipped_count
        bytes_written_total = 0

        for o in result.outputs:
            bytes_written = int(o.bytes_written or 0)
            sources_summary = str(o.sources_summary or "")
            is_already_consolidated = (
                bytes_written == 0 and sources_summary.startswith("already_consolidated")
            )

            if bytes_written > 0:
                file_action = "created"
                reused_existing = False
                files_created += 1
            elif is_already_consolidated:
                file_action = "reused"
                reused_existing = True
                files_reused += 1
            else:
                file_action = "skipped"
                reused_existing = False

            bytes_written_total += bytes_written
            outputs_payload.append(
                {
                    "id_pago": o.id_pago,
                    "cliente": o.cliente,
                    "credito": o.credito,
                    "email_pdf_path": o.email_pdf_path,
                    "asiento_pdf_path": o.asiento_pdf_path,
                    "asiento_pdf_paths": list(o.asiento_pdf_paths),
                    "extracto_pdf_path": o.extracto_pdf_path,
                    "credit_items": [dict(ci) for ci in o.credit_items],
                    "output_relative_path": o.output_relative_path,
                    "output_path": o.output_relative_path,
                    "bytes_written": bytes_written,
                    "sources_summary": o.sources_summary,
                    # Observabilidad adicional por output consolidado
                    "file_action": file_action,
                    "reused_existing": reused_existing,
                }
            )

        pdf_created = files_created > 0
        pdf_reused = files_reused > 0
        already_consolidated = bool(outputs_payload) and files_created == 0 and files_reused == len(
            outputs_payload
        )
        primary_artifact_action = (
            "created" if pdf_created else "reused" if pdf_reused else "none"
        )

        force_rebuild_used = bool(force_rebuild)
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
                    "report_date_iso": result.report_date_iso,
                    "historico_excel_path": result.historico_excel_path,
                    "estado_linea_contains": result.estado_linea_contains,
                    "email_pdf_used": result.email_pdf_used,
                    "outputs": outputs_payload,
                    "skipped": list(result.skipped),
                    "files_created": files_created,
                    "files_reused": files_reused,
                    "files_skipped": files_skipped,
                    "primary_artifact_action": primary_artifact_action,
                    "pdf_created": pdf_created,
                    "pdf_reused": pdf_reused,
                    "already_consolidated": already_consolidated,
                    "force_rebuild_used": force_rebuild_used,
                    "bytes_written_total": bytes_written_total,
                    "merge_control_file_path": result.merge_control_file_path,
                    "merge_control_updated": result.merge_control_updated,
                    "merge_control_status": result.merge_control_status,
                    "merge_manifest_path": result.merge_manifest_path,
                    "outputs_count": result.outputs_count,
                    "skipped_count": result.skipped_count,
                },
                "error": None,
            },
        )
        logger.info("job %s: merge_composite_validado_pdfs completado", job_id)
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
        logger.exception("job %s: merge_composite_validado_pdfs falló: %s", job_id, exc)
