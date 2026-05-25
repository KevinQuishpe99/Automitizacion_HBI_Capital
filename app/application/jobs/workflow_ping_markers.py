"""Markers de diagnóstico en Blob (independientes de jobs/{id}/meta.json)."""

from __future__ import annotations

from typing import Any

from app.adapters.secondary.vercel_blob_client import VercelBlobClientProtocol
from app.adapters.secondary.vercel_blob_job_store import VercelBlobJobStore
from app.application.job_store_factory import get_job_store


def _utc_now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def marker_path(job_id: str, name: str) -> str:
    return f"diagnostics/workflow-ping/{job_id}/{name}.json"


def _blob_client() -> VercelBlobClientProtocol:
    store = get_job_store()
    if isinstance(store, VercelBlobJobStore):
        return store.blob_client
    raise RuntimeError(
        "workflow_ping markers requieren VercelBlobJobStore (JOB_STORE_BACKEND=vercel_blob)"
    )


async def write_marker(job_id: str, name: str, payload: dict[str, Any] | None = None) -> None:
    blob = _blob_client()
    body = {
        "job_id": job_id,
        "marker": name,
        "timestamp": _utc_now_iso(),
        **(payload or {}),
    }
    await blob.put_json(marker_path(job_id, name), body, allow_overwrite=True)
    print(f"WORKFLOW_PING_MARKER_{name.upper()}_WRITTEN job_id={job_id}", flush=True)


async def read_marker(job_id: str, name: str) -> dict[str, Any] | None:
    blob = _blob_client()
    return await blob.get_json(marker_path(job_id, name))


async def list_markers(job_id: str) -> dict[str, bool]:
    names = ("entered", "running", "completed", "failed")
    out: dict[str, bool] = {}
    for name in names:
        data = await read_marker(job_id, name)
        out[name] = data is not None
    return out
