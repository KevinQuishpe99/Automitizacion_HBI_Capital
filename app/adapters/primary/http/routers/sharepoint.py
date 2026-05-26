import logging
import os
import uuid
from base64 import b64decode, b64encode
from datetime import datetime, timezone
from time import perf_counter
from typing import Any

import httpx
from fastapi import APIRouter, BackgroundTasks, Body, HTTPException

from app.adapters.primary.http.deps import GraphClientDep
from app.application.use_cases.sharepoint_from_env import (
    download_configured_file_base64,
    resolve_configured_item,
    upload_configured_file,
)
from app.application.use_cases.validate_payment_report import validate_payment_report_and_replace_excel
from app.application.job_status_enrichment import enrich_job_for_http_response
from app.application.job_runner_factory import get_job_runner
from app.application.job_store_factory import get_job_store
from app.domain.exceptions import GraphConfigError
from app.models import GraphUploadRequest, MergeCompositeValidadoRequest, NotifyValidarExtractosRequest

router = APIRouter(prefix="/graph/sharepoint", tags=["sharepoint"])
logger = logging.getLogger(__name__)
def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.get("/site")
async def graph_sharepoint_site(graph: GraphClientDep, hostname: str, site_path: str) -> dict:
    try:
        endpoint = f"/sites/{hostname}:{site_path}"
        return await graph.get(endpoint)
    except GraphConfigError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Graph request failed: {exc}") from exc


@router.get("/sites/{site_id}/drives")
async def graph_sharepoint_drives(graph: GraphClientDep, site_id: str) -> dict:
    try:
        return await graph.get(f"/sites/{site_id}/drives")
    except GraphConfigError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Graph request failed: {exc}") from exc


@router.get("/drives/{drive_id}/children")
async def graph_drive_children(
    graph: GraphClientDep,
    drive_id: str,
    folder_item_id: str = "root",
) -> dict:
    try:
        endpoint = f"/drives/{drive_id}/items/{folder_item_id}/children"
        return await graph.get(endpoint)
    except GraphConfigError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Graph request failed: {exc}") from exc


@router.get("/drives/{drive_id}/item-content")
async def graph_download_item_content(graph: GraphClientDep, drive_id: str, item_id: str) -> dict:
    try:
        content = await graph.get_bytes(f"/drives/{drive_id}/items/{item_id}/content")
        return {"content_base64": b64encode(content).decode("utf-8")}
    except GraphConfigError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Graph request failed: {exc}") from exc


@router.put("/drives/{drive_id}/item-content")
async def graph_update_item_content(
    graph: GraphClientDep,
    drive_id: str,
    item_id: str,
    payload: GraphUploadRequest,
) -> dict:
    try:
        file_bytes = b64decode(payload.content_base64)
        endpoint = f"/drives/{drive_id}/items/{item_id}/content"
        return await graph.put_bytes(endpoint, file_bytes)
    except GraphConfigError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Graph request failed: {exc}") from exc


@router.put("/drives/{drive_id}/path-content")
async def graph_upload_path_content(
    graph: GraphClientDep,
    drive_id: str,
    item_path: str,
    payload: GraphUploadRequest,
) -> dict:
    try:
        file_bytes = b64decode(payload.content_base64)
        endpoint = f"/drives/{drive_id}/root:/{item_path}:/content"
        return await graph.put_bytes(endpoint, file_bytes)
    except GraphConfigError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Graph request failed: {exc}") from exc


@router.get("/sites-search")
async def graph_sharepoint_sites_search(graph: GraphClientDep, search: str | None = None) -> dict:
    term = (search or "").strip()
    if not term:
        term = os.getenv("GRAPH_SHAREPOINT_SITE_SEARCH", "").strip()
    if not term:
        raise HTTPException(
            status_code=400,
            detail="Pass ?search=... or set GRAPH_SHAREPOINT_SITE_SEARCH",
        )
    try:
        return await graph.get("/sites", params={"search": term})
    except GraphConfigError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Graph request failed: {exc}") from exc


@router.get("/resolve-env")
async def graph_sharepoint_resolve_env(graph: GraphClientDep) -> dict:
    try:
        return await resolve_configured_item(graph)
    except GraphConfigError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Graph request failed: {exc}") from exc


@router.get("/excel-from-env")
async def graph_sharepoint_excel_from_env(graph: GraphClientDep) -> dict:
    try:
        return await download_configured_file_base64(graph)
    except GraphConfigError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Graph request failed: {exc}") from exc


@router.put("/file-from-env")
async def graph_sharepoint_upload_from_env(
    graph: GraphClientDep,
    payload: GraphUploadRequest,
) -> dict:
    try:
        return await upload_configured_file(graph, payload.content_base64)
    except GraphConfigError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Graph request failed: {exc}") from exc


@router.post("/validate-payment-report")
async def validate_payment_report(graph: GraphClientDep) -> dict:
    """
    Valida el Excel en GRAPH_SHAREPOINT_FILE_PATH: fecha ancla global, cuotas por PDF, empareje de
    carpetas de crédito con la columna Crédito; escribe Validado/Estado/Observaciones/Rutas y reemplaza el archivo.
    """
    # Línea explícita: si no ves logs, revisa LOG_LEVEL=INFO y que la consola sea la de uvicorn.
    logger.info("HTTP validate_payment_report: recibido request (inicio)")
    started_ts = perf_counter()
    try:
        summary = await validate_payment_report_and_replace_excel(graph)
        elapsed_ms = round((perf_counter() - started_ts) * 1000, 2)
        payload = {
            "status": "ok",
            "message": "Ejecutado con éxito",
            "reaction_time_ms": elapsed_ms,
            "processed_rows": summary.processed_rows,
            "ok_count": summary.ok_count,
            "no_count": summary.no_count,
            "error_count": summary.error_count,
            "errors": summary.errors,
        }
        logger.info(
            "HTTP validate_payment_report: completado",
            extra={
                "processed_rows": summary.processed_rows,
                "ok_count": summary.ok_count,
                "no_count": summary.no_count,
                "error_count": summary.error_count,
            },
        )
        return payload
    except GraphConfigError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code
        if code == 404:
            raise HTTPException(
                status_code=404,
                detail="El Excel configurado no existe en SharePoint (revisa GRAPH_SHAREPOINT_FILE_PATH).",
            ) from exc
        if code == 423:
            raise HTTPException(
                status_code=423,
                detail="El Excel está bloqueado (abierto/check-out). Cierra el archivo y reintenta.",
            ) from exc
        raise HTTPException(status_code=400, detail=f"Validation failed: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Validation failed: {exc}") from exc


@router.post("/validate-payment-report/queue")
async def validate_payment_report_queue(
    graph: GraphClientDep,
    background_tasks: BackgroundTasks,
) -> dict:
    """
    Encola la validación y responde inmediato con job_id para evitar timeout en cliente.
    """
    job_id = str(uuid.uuid4())
    await get_job_store().create_job(
        job_id,
        {
            "job_id": job_id,
            "status": "queued",
            "created_at": _utc_now_iso(),
            "updated_at": _utc_now_iso(),
            "started_at": None,
            "finished_at": None,
            "result": None,
            "error": None,
        },
    )
    runner = get_job_runner()
    await runner.enqueue_validate_payment_report(
        job_id=job_id,
        graph=graph,
        background_tasks=background_tasks,
    )
    logger.info("job %s: encolado validate_payment_report (%s)", job_id, type(runner).__name__)
    return {
        "status": "queued",
        "job_id": job_id,
        "estimated_processing_seconds": 60,
        "message": "Trabajo en cola. Consulta /graph/sharepoint/validate-payment-report/jobs/{job_id}",
    }


@router.get("/validate-payment-report/jobs/{job_id}")
async def validate_payment_report_job_status(job_id: str) -> dict:
    job = await get_job_store().get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/notify-validar-extractos-email/jobs/{job_id}")
async def notify_validar_extractos_job_status(job_id: str) -> dict:
    job = await get_job_store().get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return enrich_job_for_http_response(job)


@router.get("/merge-composite-validado-pdfs/jobs/{job_id}")
async def merge_composite_validado_pdfs_job_status(job_id: str) -> dict:
    job = await get_job_store().get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return enrich_job_for_http_response(job)


@router.post("/merge-composite-validado-pdfs", status_code=202)
async def post_merge_composite_validado_pdfs(
    graph: GraphClientDep,
    background_tasks: BackgroundTasks,
    body: MergeCompositeValidadoRequest | None = Body(default=None),
) -> dict[str, Any]:
    """
    Une PDFs por cada ID Pago (Estado línea según GRAPH_VALIDAR_EXTRACTO_ESTADO_CONTAINS):
    PDF del correo (05 EMAIL, una vez), luego por crédito todos los asientos y un extracto único.
    Mismo ID Pago = un solo PDF. ``force_rebuild=true`` regenera el consolidado aunque ya exista.
    Consulta ``GET …/merge-composite-validado-pdfs/jobs/{job_id}``.
    """
    payload = body or MergeCompositeValidadoRequest()
    job_id = str(uuid.uuid4())
    await get_job_store().create_job(
        job_id,
        {
            "job_id": job_id,
            "type": "merge_composite_validado_pdfs",
            "status": "queued",
            "created_at": _utc_now_iso(),
            "updated_at": _utc_now_iso(),
            "started_at": None,
            "finished_at": None,
            "result": None,
            "error": None,
            "force_rebuild": payload.force_rebuild,
        },
    )
    runner = get_job_runner()
    await runner.enqueue_merge_composite_validado_pdfs(
        job_id=job_id,
        graph=graph,
        force_rebuild=payload.force_rebuild,
        background_tasks=background_tasks,
    )
    logger.info(
        "job %s: encolado merge_composite_validado_pdfs (%s)",
        job_id,
        type(runner).__name__,
    )
    return {
        "status": "queued",
        "job_id": job_id,
        "estimated_processing_seconds": 300,
        "message": (
            "Trabajo en cola. Consulta "
            f"/graph/sharepoint/merge-composite-validado-pdfs/jobs/{job_id}"
        ),
    }


@router.post("/notify-validar-extractos-email", status_code=202)
async def notify_validar_extractos_email(
    graph: GraphClientDep,
    background_tasks: BackgroundTasks,
    body: NotifyValidarExtractosRequest | None = Body(default=None),
) -> dict:
    """
    Body JSON debe incluir ``historical_file_path``: ruta relativa al root del drive (la misma
    que ``result.historical_file_path`` de Finalize), no ``webUrl``. Sin path válido el job falla
    con ``missing_historical_file_path``.

    Lee el Excel del reporte (GRAPH_SHAREPOINT_FILE_PATH) para la tabla del correo y la fecha mínima
    en la columna Fecha. El histórico de validación **solo** se obtiene por ``historical_file_path``
    (no hay resolución automática por carpetas).

    Hoja Distribución del histórico; filas con Estado línea según GRAPH_VALIDAR_EXTRACTO_ESTADO_CONTAINS.
    Remitente y destinatarios: CORREOS.xlsx salvo overrides ``to`` / ``cc`` en el body.
    """
    payload = body or NotifyValidarExtractosRequest()
    job_id = str(uuid.uuid4())
    await get_job_store().create_job(
        job_id,
        {
            "job_id": job_id,
            "type": "notify_validar_extractos",
            "status": "queued",
            "created_at": _utc_now_iso(),
            "updated_at": _utc_now_iso(),
            "started_at": None,
            "finished_at": None,
            "result": None,
            "error": None,
        },
    )
    runner = get_job_runner()
    await runner.enqueue_notify_validar_extractos(
        job_id=job_id,
        graph=graph,
        historical_file_path=payload.historical_file_path,
        to_override=payload.to,
        cc_override=payload.cc,
        background_tasks=background_tasks,
    )
    logger.info("job %s: encolado notify_validar_extractos (%s)", job_id, type(runner).__name__)
    return {
        "status": "queued",
        "job_id": job_id,
        "estimated_processing_seconds": 180,
        "message": (
            "Trabajo en cola. Consulta "
            f"/graph/sharepoint/notify-validar-extractos-email/jobs/{job_id}"
        ),
    }


@router.post("/ensure-asientos-contables-folders", status_code=202)
async def post_ensure_asientos_contables_folders(
    graph: GraphClientDep,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    """
    Encola la creación de subcarpetas bajo cada crédito de cada cliente (GRAPH_CLIENTS_BASE_PATH):
    por defecto ``ASIENTOS CONTABLES`` y ``EXTRACTOS`` (si ya existen, no hace nada).
    Consulta el estado en ``GET /graph/sharepoint/ensure-asientos-contables-folders/jobs/{job_id}``.
    """
    job_id = str(uuid.uuid4())
    await get_job_store().create_job(
        job_id,
        {
            "job_id": job_id,
            "type": "ensure_asientos_contables",
            "status": "queued",
            "created_at": _utc_now_iso(),
            "updated_at": _utc_now_iso(),
            "started_at": None,
            "finished_at": None,
            "result": None,
            "error": None,
        },
    )
    runner = get_job_runner()
    await runner.enqueue_ensure_asientos_contables(
        job_id=job_id,
        graph=graph,
        background_tasks=background_tasks,
    )
    logger.info("job %s: encolado ensure_asientos_contables (%s)", job_id, type(runner).__name__)
    return {
        "status": "queued",
        "job_id": job_id,
        "estimated_processing_seconds": 300,
        "message": (
            "Trabajo en cola. Consulta "
            f"/graph/sharepoint/ensure-asientos-contables-folders/jobs/{job_id}"
        ),
    }


@router.get("/ensure-asientos-contables-folders/jobs/{job_id}")
async def get_ensure_asientos_contables_job_status(job_id: str) -> dict[str, Any]:
    job = await get_job_store().get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job
