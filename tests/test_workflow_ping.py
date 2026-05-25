"""Diagnóstico workflow_ping: job, runner, entrypoint y HTTP."""

from __future__ import annotations

import asyncio
import importlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.adapters.primary.http.routers import diagnostics
from app.adapters.secondary.vercel_blob_job_store import VercelBlobJobStore
from app.adapters.secondary.vercel_blob_client import InMemoryVercelBlobClient
from app.application import job_runner_factory
from app.application.job_manager import JobManager
from app.application.job_store_factory import reset_job_store_for_tests
from app.application.jobs.workflow_ping_job import execute_workflow_ping_job
from app.workflows.wf import wf


@pytest.fixture(autouse=True)
def _reset_singletons() -> None:
    reset_job_store_for_tests()
    job_runner_factory.reset_job_runner_for_tests()
    yield
    reset_job_store_for_tests()
    job_runner_factory.reset_job_runner_for_tests()


def test_workflow_entrypoint_imports_both_workflows() -> None:
    index = importlib.import_module("app.workflows.index")
    assert hasattr(index, "_amortization_dry_run_workflow")
    assert hasattr(index, "_workflow_ping_workflow")
    from app.workflows.amortization_dry_run_workflow import amortization_dry_run_workflow
    from app.workflows.workflow_ping_workflow import workflow_ping_workflow

    registered = list(wf._workflows.keys())
    assert any("amortization_dry_run_workflow" in key for key in registered)
    assert any("workflow_ping_workflow" in key for key in registered)
    assert amortization_dry_run_workflow is not None
    assert workflow_ping_workflow is not None


def test_workflow_ping_job_queued_to_completed() -> None:
    async def run() -> None:
        store = VercelBlobJobStore.with_memory_blob()
        from app.application.job_store_factory import configure_job_store

        configure_job_store(store)
        await store.create_job(
            "ping-1",
            {"job_id": "ping-1", "type": "workflow_ping", "status": "queued"},
        )
        await execute_workflow_ping_job("ping-1")
        job = await store.get_job("ping-1")
        assert job is not None
        assert job["status"] == "completed"
        assert job["result"]["message"] == "workflow ping completed"

    asyncio.run(run())


def test_workflow_ping_runner_stores_workflow_run_id(monkeypatch: pytest.MonkeyPatch) -> None:
    async def run() -> None:
        from app.adapters.secondary.vercel_workflow_job_runner import VercelWorkflowJobRunner

        store = VercelBlobJobStore.with_memory_blob()
        from app.application.job_store_factory import configure_job_store

        configure_job_store(store)
        await store.create_job("ping-2", {"job_id": "ping-2", "type": "workflow_ping", "status": "queued"})

        run_mock = MagicMock(run_id="wrun_test_ping_001")
        with patch("vercel.workflow.start", new_callable=AsyncMock, return_value=run_mock):
            runner = VercelWorkflowJobRunner()
            await runner.enqueue_workflow_ping(job_id="ping-2")

        job = await store.get_job("ping-2")
        assert job is not None
        assert job["workflow_run_id"] == "wrun_test_ping_001"
        assert job["workflow_name"] == "workflow_ping_workflow"

    asyncio.run(run())


def test_workflow_ping_queue_endpoint_background(
    workflow_ping_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("JOB_RUNNER_BACKEND", raising=False)
    monkeypatch.delenv("VERCEL_WORKFLOWS_ENABLED", raising=False)
    res = workflow_ping_client.post("/diagnostics/workflow-ping/queue")
    assert res.status_code == 202
    body = res.json()
    assert body["status"] == "queued"
    job_id = body["job_id"]
    res2 = workflow_ping_client.get(f"/diagnostics/workflow-ping/jobs/{job_id}")
    assert res2.status_code == 200


@pytest.fixture
def workflow_ping_client() -> TestClient:
    from app.application.job_store_factory import configure_job_store

    configure_job_store(VercelBlobJobStore.with_memory_blob(InMemoryVercelBlobClient()))
    app = FastAPI()
    app.include_router(diagnostics.router)
    return TestClient(app, raise_server_exceptions=False)


def test_workflow_ping_queue_endpoint_workflow_mode(
    workflow_ping_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    enqueued: list[str] = []

    class _Runner:
        async def enqueue_workflow_ping(self, *, job_id: str) -> None:
            enqueued.append(job_id)

    monkeypatch.setenv("JOB_RUNNER_BACKEND", "vercel_workflow")
    monkeypatch.setenv("VERCEL_WORKFLOWS_ENABLED", "true")
    job_runner_factory.reset_job_runner_for_tests()
    job_runner_factory.configure_job_runner(_Runner())  # type: ignore[arg-type]

    res = workflow_ping_client.post("/diagnostics/workflow-ping/queue")
    assert res.status_code == 202
    job_id = res.json()["job_id"]
    assert len(enqueued) == 1
    assert enqueued[0] == job_id
