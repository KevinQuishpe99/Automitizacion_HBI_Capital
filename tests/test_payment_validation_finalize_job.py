"""Tests del job finalize: failed/completed y no quedar en running."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.adapters.secondary.memory_job_store import MemoryJobStore
from app.application.job_manager import JobManager
from app.application.job_store_factory import configure_job_store, reset_job_store_for_tests
from app.application.jobs.payment_validation_finalize_job import (
    execute_payment_validation_finalize_job,
)


@pytest.fixture(autouse=True)
def _store():
    configure_job_store(MemoryJobStore())
    yield
    reset_job_store_for_tests()
    JobManager._instance = None


def test_finalize_job_marks_failed_when_use_case_raises():
    async def run() -> None:
        with patch(
            "app.application.jobs.payment_validation_finalize_job.finalize_payment_validation",
            new_callable=AsyncMock,
            side_effect=ValueError("process_not_approved"),
        ):
            await execute_payment_validation_finalize_job(
                "fin-1",
                MagicMock(),
                validation_file="validacion_pagos_2026-05-26.xlsx",
                validation_file_path=None,
                process_date_iso="2026-05-26",
            )

        jm = JobManager()
        job = await jm.get_job("fin-1")
        assert job is not None
        assert job["status"] == "failed"
        assert "process_not_approved" in str(job["error"]["message"])

    asyncio.run(run())


def test_finalize_job_marks_failed_on_timeout():
    async def run() -> None:
        async def slow(*_a, **_k):
            await asyncio.sleep(60)

        with patch(
            "app.application.jobs.payment_validation_finalize_job.finalize_payment_validation",
            new_callable=AsyncMock,
            side_effect=slow,
        ):
            with patch(
                "app.application.jobs.job_run_guard.job_step_timeout_seconds",
                return_value=0.2,
            ):
                await execute_payment_validation_finalize_job(
                    "fin-2",
                    MagicMock(),
                    validation_file=None,
                    validation_file_path=None,
                    process_date_iso="2026-05-26",
                )

        job = await JobManager().get_job("fin-2")
        assert job is not None
        assert job["status"] == "failed"
        assert "finalize_timeout" in str(job["error"]["message"])

    asyncio.run(run())
