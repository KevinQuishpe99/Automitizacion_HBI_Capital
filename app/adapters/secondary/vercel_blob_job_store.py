"""
JobStore durable sobre Vercel Blob (Fase 3).

Layout:
  jobs/{job_id}/meta.json
  jobs/{job_id}/result.json          (resultado inline/mediano)
  results/{job_id}/full.json         (resultado grande)
  locks/{lock_key}.json
  jobs/{job_id}/events.ndjson

Limitación locks: Blob no ofrece CAS; acquire_lock es best-effort con TTL + holder.
"""

from __future__ import annotations

import asyncio
import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any

from app.adapters.secondary.vercel_blob_client import (
    InMemoryVercelBlobClient,
    VercelBlobClientProtocol,
    create_vercel_blob_client_from_env,
)
from app.application.job_store_settings import (
    job_inline_result_max_bytes,
    job_ttl_days,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _meta_path(job_id: str) -> str:
    return f"jobs/{job_id}/meta.json"


def _result_path(job_id: str) -> str:
    return f"jobs/{job_id}/result.json"


def _full_result_path(job_id: str) -> str:
    return f"results/{job_id}/full.json"


def _events_path(job_id: str) -> str:
    return f"jobs/{job_id}/events.ndjson"


def _lock_path(lock_key: str) -> str:
    safe_key = lock_key.replace(":", "_").replace("/", "_")
    return f"locks/{safe_key}.json"


def _compute_expires_at_iso(days: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def _is_expired(expires_at: str | None) -> bool:
    from app.application.lock_utils import is_lock_expired

    return is_lock_expired(expires_at)


def _serialize_json(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def extract_result_summary(result: dict[str, Any]) -> dict[str, Any]:
    """Resumen para meta cuando el result completo va a results/{job_id}/full.json."""
    summary: dict[str, Any] = {}
    for key in (
        "status",
        "message",
        "process_date",
        "validation_file",
        "validation_file_path",
        "historical_file_path",
        "report_date_iso",
        "outputs_count",
        "skipped_count",
        "processed_rows",
        "ok_count",
        "error_count",
        "elapsed_ms",
    ):
        if key in result:
            summary[key] = result[key]
    if "summary" in result and isinstance(result["summary"], dict):
        summary["summary"] = result["summary"]
    if "outputs" in result and isinstance(result["outputs"], list):
        summary["outputs_count"] = summary.get("outputs_count") or len(result["outputs"])
    if not summary:
        summary["keys"] = list(result.keys())[:30]
    return summary


class VercelBlobJobStore:
    """Persistencia de jobs en Vercel Blob."""

    def __init__(
        self,
        blob: VercelBlobClientProtocol,
        *,
        ttl_days: int | None = None,
        inline_max_bytes: int | None = None,
        http_get_max_bytes: int | None = None,
    ) -> None:
        self._blob = blob
        self._ttl_days = ttl_days if ttl_days is not None else job_ttl_days()
        self._inline_max = inline_max_bytes if inline_max_bytes is not None else job_inline_result_max_bytes()
        # Límite al ensamblar GET (evitar respuestas HTTP enormes para PA)
        self._http_get_max = http_get_max_bytes if http_get_max_bytes is not None else self._inline_max
        self._write_lock = asyncio.Lock()

    @property
    def blob_client(self) -> VercelBlobClientProtocol:
        return self._blob

    @classmethod
    def from_env(cls) -> VercelBlobJobStore:
        return cls(create_vercel_blob_client_from_env())

    @classmethod
    def with_memory_blob(
        cls,
        blob: InMemoryVercelBlobClient | None = None,
        **kwargs: Any,
    ) -> VercelBlobJobStore:
        return cls(blob or InMemoryVercelBlobClient(), **kwargs)

    async def _read_meta(self, job_id: str) -> dict[str, Any] | None:
        meta = await self._blob.get_json(_meta_path(job_id))
        if meta is None:
            return None
        if _is_expired(meta.get("expires_at")):
            meta = dict(meta)
            meta["status"] = "expired"
        return meta

    async def _write_meta(self, job_id: str, meta: dict[str, Any]) -> None:
        record = dict(meta)
        record.setdefault("job_id", job_id)
        record.setdefault("updated_at", _utc_now_iso())
        if "expires_at" not in record:
            record["expires_at"] = _compute_expires_at_iso(self._ttl_days)
        await self._blob.put_json(_meta_path(job_id), record, allow_overwrite=True)

    async def _persist_result(self, job_id: str, meta: dict[str, Any], result: Any) -> dict[str, Any]:
        if result is None:
            meta.pop("result_ref", None)
            meta.pop("result_summary", None)
            meta["result"] = None
            return meta

        if not isinstance(result, dict):
            meta["result"] = result
            meta.pop("result_ref", None)
            meta.pop("result_summary", None)
            return meta

        payload = _serialize_json(result)
        if len(payload) <= self._inline_max:
            await self._blob.put_json(_result_path(job_id), result, allow_overwrite=True)
            meta["result"] = result
            meta["result_ref"] = _result_path(job_id)
            meta.pop("result_summary", None)
            return meta

        await self._blob.put_json(_full_result_path(job_id), result, allow_overwrite=True)
        meta.pop("result", None)
        meta["result_ref"] = _full_result_path(job_id)
        meta["result_summary"] = extract_result_summary(result)
        return meta

    async def _load_result_for_get(self, meta: dict[str, Any]) -> dict[str, Any]:
        """Ensambla job para GET; no incluye resultados que excedan http_get_max."""
        job = dict(meta)
        if job.get("status") == "expired":
            return job

        inline = job.get("result")
        if inline is not None:
            payload = _serialize_json(inline)
            if len(payload) > self._http_get_max:
                job.pop("result", None)
                job.setdefault("result_summary", extract_result_summary(inline if isinstance(inline, dict) else {"value": inline}))
            return job

        ref = job.get("result_ref")
        if not ref:
            return job

        raw = await self._blob.get_bytes(ref)
        if raw is None:
            return job

        if len(raw) > self._http_get_max:
            if not job.get("result_summary") and ref.endswith("/full.json"):
                try:
                    full = json.loads(raw.decode("utf-8"))
                    if isinstance(full, dict):
                        job["result_summary"] = extract_result_summary(full)
                except json.JSONDecodeError:
                    pass
            return job

        try:
            job["result"] = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            job["result"] = None
        return job

    async def create_job(self, job_id: str, record: dict[str, Any]) -> None:
        async with self._write_lock:
            meta = deepcopy(record)
            meta.setdefault("job_id", job_id)
            meta.setdefault("created_at", meta.get("created_at") or _utc_now_iso())
            meta.setdefault("queued_at", meta.get("queued_at") or meta.get("created_at"))
            meta.setdefault("updated_at", _utc_now_iso())
            meta["expires_at"] = _compute_expires_at_iso(self._ttl_days)
            if "result" in meta and meta["result"] is not None:
                meta = await self._persist_result(job_id, meta, meta.pop("result"))
            await self._write_meta(job_id, meta)

    async def get_job(self, job_id: str) -> dict[str, Any] | None:
        meta = await self._read_meta(job_id)
        if meta is None:
            return None
        return await self._load_result_for_get(meta)

    async def update_job(self, job_id: str, updates: dict[str, Any]) -> None:
        async with self._write_lock:
            meta = await self._read_meta(job_id) or {"job_id": job_id}
            meta = dict(meta)
            updates_copy = dict(updates)
            if "result" in updates_copy:
                result = updates_copy.pop("result")
                meta = await self._persist_result(job_id, meta, result)
            meta.update(updates_copy)
            meta["updated_at"] = _utc_now_iso()
            await self._write_meta(job_id, meta)

    async def complete_job(self, job_id: str, result: dict[str, Any]) -> None:
        async with self._write_lock:
            meta = await self._read_meta(job_id) or {"job_id": job_id}
            meta = dict(meta)
            meta["status"] = "completed"
            meta["error"] = None
            meta = await self._persist_result(job_id, meta, result)
            meta["updated_at"] = _utc_now_iso()
            await self._write_meta(job_id, meta)

    async def fail_job(self, job_id: str, error: dict[str, Any]) -> None:
        await self.update_job(
            job_id,
            {"status": "failed", "error": error, "result": None},
        )

    async def append_event(self, job_id: str, event: dict[str, Any]) -> None:
        path = _events_path(job_id)
        line = json.dumps({**event, "at": _utc_now_iso()}, ensure_ascii=False) + "\n"
        existing = await self._blob.get_bytes(path) or b""
        await self._blob.put_bytes(
            path,
            existing + line.encode("utf-8"),
            content_type="application/x-ndjson",
            allow_overwrite=True,
        )

    async def acquire_lock(self, key: str, holder: str, ttl_seconds: int) -> bool:
        path = _lock_path(key)
        now = datetime.now(timezone.utc)
        existing = await self._blob.get_json(path)
        if existing is not None:
            expires_at = existing.get("expires_at")
            if expires_at and not _is_expired(expires_at) and existing.get("holder") != holder:
                return False

        record = {
            "lock_key": key,
            "holder": holder,
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(seconds=ttl_seconds)).isoformat(),
        }
        await self._blob.put_json(path, record, allow_overwrite=True)
        # Re-read best-effort: otro worker pudo ganar la carrera
        check = await self._blob.get_json(path)
        if check and check.get("holder") != holder and not _is_expired(check.get("expires_at")):
            return False
        return True

    async def get_lock(self, key: str) -> dict[str, Any] | None:
        return await self._blob.get_json(_lock_path(key))

    async def cleanup_expired_lock(self, key: str) -> bool:
        path = _lock_path(key)
        existing = await self._blob.get_json(path)
        if existing is None:
            return False
        if _is_expired(existing.get("expires_at")):
            await self._blob.delete(path)
            return True
        return False

    async def release_lock(self, key: str, holder: str) -> None:
        path = _lock_path(key)
        existing = await self._blob.get_json(path)
        if existing and existing.get("holder") == holder:
            await self._blob.delete(path)

    async def is_lock_held(self, key: str) -> bool:
        path = _lock_path(key)
        existing = await self._blob.get_json(path)
        if existing is None:
            return False
        if _is_expired(existing.get("expires_at")):
            await self._blob.delete(path)
            return False
        return True
