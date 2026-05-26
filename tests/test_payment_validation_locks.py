"""Tests de locks generate/finalize (TTL, expiración, diagnóstico)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.adapters.secondary.memory_job_store import MemoryJobStore
from app.application.job_manager import JobManager
from app.application.job_store_factory import (
    _LOCK_FINALIZE,
    _LOCK_GENERATE,
    _LOCK_HOLDER,
    configure_job_store,
    lock_ttl_seconds,
    reset_job_store_for_tests,
)
from app.application.payment_validation_locks import (
    cleanup_expired_payment_validation_locks,
    detailed_lock_status,
    release_stale_lock_admin,
)


@pytest.fixture(autouse=True)
def _memory_store():
    configure_job_store(MemoryJobStore())
    yield
    reset_job_store_for_tests()
    JobManager._instance = None


def test_lock_ttl_uses_env_not_hardcoded_24h(monkeypatch):
    monkeypatch.setenv("LOCK_TTL_SECONDS", "1800")
    from app.application.job_store_settings import default_lock_ttl_seconds

    assert default_lock_ttl_seconds() == 1800
    assert lock_ttl_seconds() == 1800


def test_finalize_job_releases_lock_on_success():
    async def run() -> None:
        jm = JobManager()
        assert await jm.try_start_finalize() is True
        await jm.finish_finalize()
        store = jm.store
        assert await store.is_lock_held(_LOCK_FINALIZE) is False

    asyncio.run(run())


def test_finalize_job_releases_lock_on_exception():
    async def run() -> None:
        jm = JobManager()
        assert await jm.try_start_finalize() is True
        try:
            raise RuntimeError("boom")
        except RuntimeError:
            pass
        finally:
            await jm.finish_finalize()
        assert await jm.store.is_lock_held(_LOCK_FINALIZE) is False

    asyncio.run(run())


def test_generate_job_releases_lock_on_exception():
    async def run() -> None:
        jm = JobManager()
        assert await jm.try_start_generate() is True
        try:
            raise ValueError("fail")
        except ValueError:
            pass
        finally:
            await jm.finish_generate()
        assert await jm.store.is_lock_held(_LOCK_GENERATE) is False

    asyncio.run(run())


def test_is_lock_held_false_when_expired():
    async def run() -> None:
        store = MemoryJobStore()
        past = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
        store._locks[_LOCK_FINALIZE] = {
            "lock_key": _LOCK_FINALIZE,
            "holder": _LOCK_HOLDER,
            "created_at": past,
            "expires_at": past,
        }
        assert await store.is_lock_held(_LOCK_FINALIZE) is False
        assert await store.get_lock(_LOCK_FINALIZE) is None

    asyncio.run(run())


def test_acquire_lock_replaces_expired():
    async def run() -> None:
        store = MemoryJobStore()
        past = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()
        store._locks[_LOCK_FINALIZE] = {
            "holder": "other",
            "created_at": past,
            "expires_at": past,
        }
        ok = await store.acquire_lock(_LOCK_FINALIZE, _LOCK_HOLDER, 60)
        assert ok is True
        assert await store.is_lock_held(_LOCK_FINALIZE) is True

    asyncio.run(run())


def test_expired_finalize_lock_does_not_block_generate():
    async def run() -> None:
        store = MemoryJobStore()
        configure_job_store(store)
        past = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        store._locks[_LOCK_FINALIZE] = {
            "holder": _LOCK_HOLDER,
            "created_at": past,
            "expires_at": past,
        }
        jm = JobManager()
        assert await jm.try_start_generate() is True
        await jm.finish_generate()

    asyncio.run(run())


def test_cleanup_expired_removes_only_expired():
    async def run() -> None:
        store = MemoryJobStore()
        configure_job_store(store)
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        store._locks[_LOCK_FINALIZE] = {
            "holder": _LOCK_HOLDER,
            "created_at": past,
            "expires_at": past,
        }
        store._locks[_LOCK_GENERATE] = {
            "holder": _LOCK_HOLDER,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": future,
        }
        result = await cleanup_expired_payment_validation_locks()
        assert _LOCK_FINALIZE in result["cleaned"]
        assert _LOCK_GENERATE not in result["cleaned"]
        assert result["locks"]["finalize"]["held"] is False
        assert result["locks"]["generate"]["held"] is True

    asyncio.run(run())


def test_detailed_lock_status_shape():
    async def run() -> None:
        jm = JobManager()
        await jm.try_start_finalize()
        status = await detailed_lock_status()
        fin = status["finalize"]
        assert "held" in fin
        assert "expires_at" in fin
        assert "expired" in fin
        assert "seconds_until_expiry" in fin
        await jm.finish_finalize()

    asyncio.run(run())


def test_release_stale_requires_confirm():
    async def run() -> None:
        jm = JobManager()
        await jm.try_start_finalize()
        out = await release_stale_lock_admin(lock_key=_LOCK_FINALIZE, confirm=False)
        assert out["released"] is False
        assert await jm.store.is_lock_held(_LOCK_FINALIZE) is True
        out2 = await release_stale_lock_admin(lock_key=_LOCK_FINALIZE, confirm=True)
        assert out2["released"] is True
        assert await jm.store.is_lock_held(_LOCK_FINALIZE) is False

    asyncio.run(run())
