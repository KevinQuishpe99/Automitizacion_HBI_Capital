"""Fallback API cuando el worker Vercel no avanza el job tras workflow.start."""

from __future__ import annotations

import asyncio

import pytest

from app.adapters.secondary.memory_job_store import MemoryJobStore
from app.application.job_store_factory import configure_job_store, reset_job_store_singleton
from app.application.jobs.vercel_workflow_fallback import (
    run_job_if_still_queued,
    workflow_api_fallback_enabled,
)


@pytest.fixture(autouse=True)
def _memory_store() -> None:
    reset_job_store_singleton()
    configure_job_store(MemoryJobStore())
    yield
    reset_job_store_singleton()


def test_workflow_api_fallback_enabled_on_vercel(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VERCEL_WORKFLOW_API_FALLBACK", raising=False)
    monkeypatch.setenv("VERCEL", "1")
    assert workflow_api_fallback_enabled() is True


def test_workflow_api_fallback_disabled_by_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("VERCEL_WORKFLOW_API_FALLBACK", "false")
    assert workflow_api_fallback_enabled() is False


def test_run_job_if_still_queued_executes_when_stuck() -> None:
    from app.application.job_store_factory import get_job_store

    async def _run() -> None:
        store = get_job_store()
        await store.create_job("j1", {"job_id": "j1", "status": "queued"})
        executed: list[str] = []

        async def execute() -> None:
            executed.append("ok")
            await store.update_job("j1", {"status": "completed"})

        await run_job_if_still_queued("j1", execute=execute, label="test", delay_seconds=0.1)
        assert executed == ["ok"]

    asyncio.run(_run())


def test_run_job_if_still_queued_skips_when_running_recent() -> None:
    from datetime import datetime, timedelta, timezone

    from app.application.job_store_factory import get_job_store

    async def _run() -> None:
        store = get_job_store()
        now = datetime.now(timezone.utc).isoformat()
        await store.create_job(
            "j2",
            {"job_id": "j2", "status": "running", "started_at": now},
        )
        executed: list[str] = []

        async def execute() -> None:
            executed.append("ok")

        await run_job_if_still_queued("j2", execute=execute, label="test", delay_seconds=0.05)
        assert executed == []

    asyncio.run(_run())


def test_run_job_if_still_queued_marks_stale_running_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    from datetime import datetime, timedelta, timezone

    from app.application.job_store_factory import get_job_store

    monkeypatch.setenv("VERCEL_WORKFLOW_STALE_RUNNING_SECONDS", "30")

    async def _run() -> None:
        store = get_job_store()
        old = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
        await store.create_job(
            "j3",
            {"job_id": "j3", "status": "running", "started_at": old},
        )

        async def execute() -> None:
            raise AssertionError("no debe ejecutar si ya estaba running estancado")

        await run_job_if_still_queued("j3", execute=execute, label="finalize", delay_seconds=0.05)
        job = await store.get_job("j3")
        assert job is not None
        assert job["status"] == "failed"
        assert job["error"]["error_code"] == "job_stuck_running"

    asyncio.run(_run())
