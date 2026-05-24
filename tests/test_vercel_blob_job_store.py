"""Tests de VercelBlobJobStore con cliente Blob en memoria (sin red)."""

import asyncio
import json
import os
from datetime import datetime, timedelta, timezone

import pytest

from app.adapters.secondary.vercel_blob_client import InMemoryVercelBlobClient
from app.adapters.secondary.vercel_blob_job_store import (
    VercelBlobJobStore,
    _lock_path,
    extract_result_summary,
)
from app.application.job_store_factory import (
    _resolve_job_store,
    configure_job_store,
    get_job_store,
    reset_job_store_for_tests,
)
from app.adapters.secondary.memory_job_store import MemoryJobStore
from app.application.job_status_enrichment import enrich_job_for_http_response


@pytest.fixture
def blob() -> InMemoryVercelBlobClient:
    b = InMemoryVercelBlobClient()
    yield b
    b.clear()


@pytest.fixture
def store(blob: InMemoryVercelBlobClient) -> VercelBlobJobStore:
    return VercelBlobJobStore.with_memory_blob(
        blob,
        ttl_days=7,
        inline_max_bytes=512,
        http_get_max_bytes=512,
    )


def test_create_and_get_job(store: VercelBlobJobStore) -> None:
    async def run() -> None:
        await store.create_job(
            "j1",
            {
                "job_id": "j1",
                "type": "generate",
                "status": "queued",
                "request": {"x": 1},
            },
        )
        job = await store.get_job("j1")
        assert job is not None
        assert job["status"] == "queued"
        assert job["type"] == "generate"
        assert job.get("expires_at")

    asyncio.run(run())


def test_update_job(store: VercelBlobJobStore) -> None:
    async def run() -> None:
        await store.create_job("j2", {"job_id": "j2", "status": "queued"})
        await store.update_job("j2", {"status": "running", "started_at": "t0"})
        job = await store.get_job("j2")
        assert job is not None
        assert job["status"] == "running"

    asyncio.run(run())


def test_complete_job_small_result(store: VercelBlobJobStore, blob: InMemoryVercelBlobClient) -> None:
    async def run() -> None:
        await store.create_job("j3", {"job_id": "j3", "status": "queued", "type": "generate"})
        await store.complete_job("j3", {"status": "ok", "validation_file": "a.xlsx"})
        job = await store.get_job("j3")
        assert job is not None
        assert job["status"] == "completed"
        assert job["result"]["validation_file"] == "a.xlsx"
        assert await blob.get_bytes("jobs/j3/result.json") is not None

    asyncio.run(run())


def test_complete_job_large_result_uses_result_ref(store: VercelBlobJobStore) -> None:
    async def run() -> None:
        await store.create_job("j4", {"job_id": "j4", "status": "queued", "type": "merge_composite_validado_pdfs"})
        big = {"status": "ok", "outputs": [{"id": i, "data": "x" * 200} for i in range(20)]}
        await store.complete_job("j4", big)
        job = await store.get_job("j4")
        assert job is not None
        assert job["status"] == "completed"
        assert job.get("result_ref") == "results/j4/full.json"
        assert "result_summary" in job
        assert "result" not in job or job.get("result") is None

    asyncio.run(run())


def test_fail_job(store: VercelBlobJobStore) -> None:
    async def run() -> None:
        await store.create_job("j5", {"job_id": "j5", "status": "queued"})
        await store.fail_job("j5", {"type": "ValueError", "message": "boom"})
        job = await store.get_job("j5")
        assert job is not None
        assert job["status"] == "failed"
        assert job["error"]["message"] == "boom"

    asyncio.run(run())


def test_append_event(store: VercelBlobJobStore, blob: InMemoryVercelBlobClient) -> None:
    async def run() -> None:
        await store.create_job("j6", {"job_id": "j6", "status": "running"})
        await store.append_event("j6", {"step": "a"})
        raw = await blob.get_bytes("jobs/j6/events.ndjson")
        assert raw is not None
        assert b'"step": "a"' in raw

    asyncio.run(run())


def test_acquire_lock_when_missing(store: VercelBlobJobStore) -> None:
    async def run() -> None:
        ok = await store.acquire_lock("k1", "holder-a", 60)
        assert ok is True
        assert await store.is_lock_held("k1") is True

    asyncio.run(run())


def test_acquire_lock_denied_when_held(store: VercelBlobJobStore) -> None:
    async def run() -> None:
        assert await store.acquire_lock("k2", "a", 3600) is True
        assert await store.acquire_lock("k2", "b", 3600) is False

    asyncio.run(run())


def test_acquire_lock_replaces_expired(store: VercelBlobJobStore, blob: InMemoryVercelBlobClient) -> None:
    async def run() -> None:
        path = _lock_path("k3")
        expired = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
        await blob.put_json(
            path,
            {
                "lock_key": "k3",
                "holder": "old",
                "created_at": expired,
                "expires_at": expired,
            },
        )
        ok = await store.acquire_lock("k3", "new", 60)
        assert ok is True
        doc = await blob.get_json(path)
        assert doc["holder"] == "new"

    asyncio.run(run())


def test_release_lock_only_matching_holder(store: VercelBlobJobStore) -> None:
    async def run() -> None:
        await store.acquire_lock("k4", "owner", 60)
        await store.release_lock("k4", "other")
        assert await store.is_lock_held("k4") is True
        await store.release_lock("k4", "owner")
        assert await store.is_lock_held("k4") is False

    asyncio.run(run())


def test_get_job_enrichment_contract(store: VercelBlobJobStore) -> None:
    async def run() -> None:
        await store.create_job(
            "j7",
            {
                "job_id": "j7",
                "type": "generate",
                "status": "completed",
                "result": {
                    "validation_file": "f.xlsx",
                    "validation_file_path": "rev/f.xlsx",
                    "process_id": "p",
                    "process_date": "2026-05-01",
                    "summary": {"pagos_banco": 1, "errores": 0},
                },
            },
        )
        job = await store.get_job("j7")
        assert job is not None
        enriched = enrich_job_for_http_response(job)
        assert enriched["severity"] == "success"
        assert "user_message" in enriched

    asyncio.run(run())


def test_extract_result_summary() -> None:
    s = extract_result_summary({"status": "ok", "outputs": [1, 2], "message": "done"})
    assert s["status"] == "ok"
    assert s["outputs_count"] == 2


def test_factory_defaults_to_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JOB_STORE_BACKEND", raising=False)
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.delenv("BLOB_READ_WRITE_TOKEN", raising=False)
    from app.application.job_store_factory import reset_job_store_singleton

    reset_job_store_singleton()
    store = _resolve_job_store()
    assert isinstance(store, MemoryJobStore)


def test_factory_selects_vercel_blob_with_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JOB_STORE_BACKEND", "vercel_blob")
    monkeypatch.setenv("BLOB_READ_WRITE_TOKEN", "vercel_blob_rw_teststoreid_abc123")
    from app.application.job_store_factory import reset_job_store_singleton

    reset_job_store_singleton()
    monkeypatch.setattr(
        "app.application.job_store_factory._create_vercel_blob_store",
        lambda: VercelBlobJobStore.with_memory_blob(),
    )
    store = _resolve_job_store()
    from app.adapters.secondary.vercel_blob_job_store import VercelBlobJobStore as VBJS

    assert isinstance(store, VBJS)


def test_factory_auto_vercel_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JOB_STORE_BACKEND", raising=False)
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("BLOB_READ_WRITE_TOKEN", "vercel_blob_rw_teststoreid_abc123")
    from app.application.job_store_factory import reset_job_store_singleton

    reset_job_store_singleton()
    monkeypatch.setattr(
        "app.application.job_store_factory._create_vercel_blob_store",
        lambda: VercelBlobJobStore.with_memory_blob(),
    )
    store = _resolve_job_store()
    from app.adapters.secondary.vercel_blob_job_store import VercelBlobJobStore as VBJS

    assert isinstance(store, VBJS)
