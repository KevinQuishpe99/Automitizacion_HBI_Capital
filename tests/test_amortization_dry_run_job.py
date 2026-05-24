"""Ejecución compartida del job amortization_dry_run (JobStore)."""

import asyncio

import pytest

from app.application.job_manager import JobManager
from app.application.job_store_factory import reset_job_store_for_tests
from app.application.jobs.amortization_dry_run_job import execute_amortization_dry_run_job


@pytest.fixture(autouse=True)
def _reset():
    reset_job_store_for_tests()
    yield
    reset_job_store_for_tests()


def test_execute_completes_job(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_run(graph, **kwargs):
        return {
            "status": "ok",
            "mode": "dry_run",
            "manifest_path": "LOGS/x.json",
            "items": [],
            "summary": {"total": 0},
        }

    monkeypatch.setattr(
        "app.application.jobs.amortization_dry_run_job.run_amortization_fill_dry_run",
        fake_run,
    )

    async def run() -> None:
        await execute_amortization_dry_run_job(
            "job-1",
            object(),
            report_date_iso="2026-05-15",
            merge_manifest_path=None,
            historical_file_path=None,
        )
        jm = JobManager()
        job = await jm.get_job("job-1")
        assert job is not None
        assert job["status"] == "completed"
        assert job["result"]["mode"] == "dry_run"
        assert "elapsed_ms" in job["result"]

    asyncio.run(run())


def test_execute_failed_value_error_compatible(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_run(graph, **kwargs):
        raise ValueError("merge_manifest_not_found|LOGS/x.json")

    monkeypatch.setattr(
        "app.application.jobs.amortization_dry_run_job.run_amortization_fill_dry_run",
        fake_run,
    )

    async def run() -> None:
        await execute_amortization_dry_run_job(
            "job-2",
            object(),
            report_date_iso="2026-05-15",
            merge_manifest_path=None,
            historical_file_path=None,
        )
        jm = JobManager()
        job = await jm.get_job("job-2")
        assert job is not None
        assert job["status"] == "failed"
        assert job["error"]["type"] == "ValueError"
        assert job["error"]["error_code"] == "merge_manifest_not_found"

    asyncio.run(run())
