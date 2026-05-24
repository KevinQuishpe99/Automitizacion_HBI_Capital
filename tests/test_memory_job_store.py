"""Tests de MemoryJobStore (Fase 2 migración Vercel)."""

import asyncio

import pytest

from app.adapters.secondary.memory_job_store import MemoryJobStore
from app.application.job_store_factory import _LOCK_HOLDER, _LOCK_TTL_SECONDS


@pytest.fixture
def store() -> MemoryJobStore:
    return MemoryJobStore()


def test_create_get_update_job(store: MemoryJobStore) -> None:
    async def run() -> None:
        await store.create_job("j1", {"job_id": "j1", "status": "queued", "type": "test"})
        job = await store.get_job("j1")
        assert job is not None
        assert job["status"] == "queued"

        await store.update_job("j1", {"status": "running"})
        job = await store.get_job("j1")
        assert job is not None
        assert job["status"] == "running"

    asyncio.run(run())


def test_complete_and_fail_job(store: MemoryJobStore) -> None:
    async def run() -> None:
        await store.create_job("j2", {"job_id": "j2", "status": "queued"})
        await store.complete_job("j2", {"ok": True})
        job = await store.get_job("j2")
        assert job is not None
        assert job["status"] == "completed"
        assert job["result"] == {"ok": True}

        await store.create_job("j3", {"job_id": "j3", "status": "queued"})
        await store.fail_job("j3", {"type": "ValueError", "message": "x"})
        failed = await store.get_job("j3")
        assert failed is not None
        assert failed["status"] == "failed"
        assert failed["error"] == {"type": "ValueError", "message": "x"}

    asyncio.run(run())


def test_lock_acquire_release_and_conflict(store: MemoryJobStore) -> None:
    async def run() -> None:
        ok1 = await store.acquire_lock("k1", "holder-a", _LOCK_TTL_SECONDS)
        assert ok1 is True
        assert await store.is_lock_held("k1") is True

        ok2 = await store.acquire_lock("k1", "holder-b", _LOCK_TTL_SECONDS)
        assert ok2 is False

        await store.release_lock("k1", "holder-a")
        assert await store.is_lock_held("k1") is False

        ok3 = await store.acquire_lock("k1", "holder-b", _LOCK_TTL_SECONDS)
        assert ok3 is True

    asyncio.run(run())


def test_job_manager_enforces_generate_finalize_mutual_exclusion() -> None:
    """La exclusión generate/finalize la aplica JobManager, no una sola clave de lock."""
    from app.application.job_manager import JobManager
    from app.application.job_store_factory import reset_job_store_for_tests

    reset_job_store_for_tests()

    async def run() -> None:
        jm = JobManager()
        assert await jm.try_start_generate() is True
        assert await jm.try_start_finalize() is False
        await jm.finish_generate()

    asyncio.run(run())


def test_append_event(store: MemoryJobStore) -> None:
    async def run() -> None:
        await store.create_job("j4", {"job_id": "j4", "status": "running"})
        await store.append_event("j4", {"step": "a"})
        job = await store.get_job("j4")
        assert job is not None
        assert job["events"] == [{"step": "a"}]

    asyncio.run(run())
