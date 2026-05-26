"""Tests de idempotencia y estado terminal en job_run_guard."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from app.adapters.secondary.memory_job_store import MemoryJobStore
from app.application.job_manager import JobManager
from app.application.job_store_factory import configure_job_store, reset_job_store_singleton
from app.application.jobs.job_run_guard import (
    JobExecutionSkipped,
    begin_job_execution,
    run_job_body,
)


@pytest.fixture(autouse=True)
def _memory_store() -> None:
    reset_job_store_singleton()
    JobManager._instance = None
    configure_job_store(MemoryJobStore())
    yield
    reset_job_store_singleton()
    JobManager._instance = None


def test_begin_job_execution_skips_when_already_running() -> None:
    async def run() -> None:
        from app.application.job_store_factory import get_job_store

        store = get_job_store()
        await store.create_job("j1", {"job_id": "j1", "status": "running"})
        jm = JobManager()
        with pytest.raises(JobExecutionSkipped):
            await begin_job_execution(jm, "j1")

    asyncio.run(run())


def test_run_job_body_does_not_false_fail_when_already_completed() -> None:
    async def run() -> None:
        from app.application.job_store_factory import get_job_store

        store = get_job_store()
        await store.create_job(
            "g1",
            {
                "job_id": "g1",
                "status": "completed",
                "result": {"validation_file_path": "/x.xlsx"},
            },
        )
        jm = JobManager()
        finish_lock = AsyncMock()

        async def execute() -> None:
            await begin_job_execution(jm, "g1")

        await run_job_body(
            jm,
            "g1",
            job_label="generate",
            finish_lock=finish_lock,
            execute=execute,
        )

        job = await jm.get_job("g1")
        assert job is not None
        assert job["status"] == "completed"

    asyncio.run(run())


def test_run_job_body_reconciles_result_when_still_running() -> None:
    async def run() -> None:
        from app.application.job_store_factory import get_job_store

        store = get_job_store()
        await store.create_job(
            "g2",
            {
                "job_id": "g2",
                "status": "running",
                "result": {"ok": True},
            },
        )
        jm = JobManager()
        finish_lock = AsyncMock()

        async def execute() -> None:
            pass

        await run_job_body(
            jm,
            "g2",
            job_label="generate",
            finish_lock=finish_lock,
            execute=execute,
        )

        job = await jm.get_job("g2")
        assert job is not None
        assert job["status"] == "completed"

    asyncio.run(run())
