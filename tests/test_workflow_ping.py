"""Diagnóstico workflow_ping: job, runner, entrypoint y HTTP."""

from __future__ import annotations

import asyncio
import importlib
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.adapters.primary.http.routers import diagnostics
from app.adapters.secondary.vercel_blob_client import InMemoryVercelBlobClient
from app.adapters.secondary.vercel_blob_job_store import VercelBlobJobStore
from app.application import job_runner_factory
from app.application.job_store_factory import (
    _resolve_job_store,
    reset_job_store_for_tests,
    reset_job_store_singleton,
)
from app.application.jobs.workflow_ping_job import execute_workflow_ping_job
from app.application.jobs.workflow_ping_markers import list_markers, read_marker
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

    from app.workflows.workflow_ping_workflow import workflow_ping_step

    registered = list(wf._workflows.keys())
    assert any("amortization_dry_run_workflow" in key for key in registered)
    assert any("workflow_ping_workflow" in key for key in registered)
    assert amortization_dry_run_workflow is not None
    assert workflow_ping_workflow is not None
    step_keys = list(wf._steps.keys())
    assert any("workflow_ping_step" in key for key in step_keys)
    assert workflow_ping_step is not None


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
        markers = await list_markers("ping-1")
        assert markers == {"entered": True, "running": True, "completed": True, "failed": False}

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
    assert body["type"] == "workflow_ping"
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


def test_job_store_auto_uses_blob_with_token_without_vercel_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Worker Services puede no tener VERCEL=1; con token debe usar Blob."""
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.delenv("JOB_STORE_BACKEND", raising=False)
    monkeypatch.setenv("BLOB_READ_WRITE_TOKEN", "vercel_blob_rw_teststoreid_abc123")
    reset_job_store_singleton()

    store = _resolve_job_store()
    assert isinstance(store, VercelBlobJobStore)


def test_job_store_explicit_vercel_blob_without_vercel_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.setenv("JOB_STORE_BACKEND", "vercel_blob")
    monkeypatch.setenv("BLOB_READ_WRITE_TOKEN", "vercel_blob_rw_teststoreid_abc123")
    reset_job_store_singleton()

    store = _resolve_job_store()
    assert isinstance(store, VercelBlobJobStore)


def test_workflow_ping_marks_failed_on_exception() -> None:
    async def run() -> None:
        store = VercelBlobJobStore.with_memory_blob()
        from app.application.job_store_factory import configure_job_store

        configure_job_store(store)
        await store.create_job("ping-fail", {"job_id": "ping-fail", "type": "workflow_ping", "status": "queued"})

        async def bad_complete(job_id: str, result: dict) -> None:
            raise RuntimeError("simulated worker failure")

        with patch.object(store, "complete_job", bad_complete):
            with pytest.raises(RuntimeError, match="simulated"):
                await execute_workflow_ping_job("ping-fail")

        job = await store.get_job("ping-fail")
        assert job is not None
        assert job["status"] == "failed"
        assert job["error"]["type"] == "RuntimeError"
        markers = await list_markers("ping-fail")
        assert markers["failed"] is True
        failed_marker = await read_marker("ping-fail", "failed")
        assert failed_marker is not None
        assert failed_marker["error_type"] == "RuntimeError"

    asyncio.run(run())


def test_workflow_ping_get_wrong_type_returns_detail(workflow_ping_client: TestClient) -> None:
    async def seed() -> None:
        store = VercelBlobJobStore.with_memory_blob(InMemoryVercelBlobClient())
        from app.application.job_store_factory import configure_job_store

        configure_job_store(store)
        await store.create_job(
            "other-job",
            {
                "job_id": "other-job",
                "type": "generate",
                "status": "queued",
                "workflow_name": "some_workflow",
                "workflow_run_id": "wrun_other",
            },
        )

    asyncio.run(seed())
    res = workflow_ping_client.get("/diagnostics/workflow-ping/jobs/other-job")
    assert res.status_code == 404
    detail = res.json()["detail"]
    assert detail["error"] == "Job is not workflow_ping"
    assert detail["actual_type"] == "generate"
    assert detail["workflow_run_id"] == "wrun_other"


def test_job_raw_safe_endpoint(workflow_ping_client: TestClient) -> None:
    res = workflow_ping_client.post("/diagnostics/workflow-ping/queue")
    job_id = res.json()["job_id"]
    raw = workflow_ping_client.get(f"/diagnostics/jobs/{job_id}/raw-safe")
    assert raw.status_code == 200
    body = raw.json()
    assert body["job_id"] == job_id
    assert body["type"] == "workflow_ping"
    assert body["status"] in ("queued", "running", "completed", "failed")
    assert body["meta_source"] == "vercel_blob"
    assert "request_keys" in body


def test_workflow_ping_markers_endpoint(workflow_ping_client: TestClient) -> None:
    res = workflow_ping_client.post("/diagnostics/workflow-ping/queue")
    job_id = res.json()["job_id"]
    markers_res = workflow_ping_client.get(f"/diagnostics/workflow-ping/jobs/{job_id}/markers")
    assert markers_res.status_code == 200
    body = markers_res.json()
    assert body["job_id"] == job_id
    assert set(body["markers"].keys()) == {"entered", "running", "completed", "failed"}


def test_vercel_workflow_runner_starts_decorated_ping_workflow(monkeypatch: pytest.MonkeyPatch) -> None:
    async def run() -> None:
        from app.adapters.secondary.vercel_workflow_job_runner import VercelWorkflowJobRunner
        from app.workflows.workflow_ping_workflow import workflow_ping_workflow

        captured: dict = {}

        async def fake_start(fn, job_id: str, **kwargs):
            captured["fn"] = fn
            captured["job_id"] = job_id
            return MagicMock(run_id="wrun_ref_test")

        with patch("vercel.workflow.start", new_callable=AsyncMock, side_effect=fake_start):
            runner = VercelWorkflowJobRunner()
            await runner.enqueue_workflow_ping(job_id="ping-ref")

        assert captured["job_id"] == "ping-ref"
        assert captured["fn"] is workflow_ping_workflow

    asyncio.run(run())


def test_runtime_config_safe_endpoint(workflow_ping_client: TestClient) -> None:
    res = workflow_ping_client.get("/diagnostics/runtime-config-safe")
    assert res.status_code == 200
    body = res.json()
    assert "job_store_backend" in body
    assert "has_blob_token" in body
    assert "store_class" in body


def test_workflow_ping_queue_endpoint_workflow_mode(
    workflow_ping_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    enqueued: list[str] = []

    class _Runner:
        async def enqueue_workflow_ping(
            self, *, job_id: str, background_tasks: Any = None
        ) -> None:
            enqueued.append(job_id)

    monkeypatch.setenv("JOB_RUNNER_BACKEND", "vercel_workflow")
    monkeypatch.setenv("VERCEL_WORKFLOWS_ENABLED", "true")
    job_runner_factory.reset_job_runner_for_tests()
    job_runner_factory.configure_job_runner(_Runner())  # type: ignore[arg-type]

    res = workflow_ping_client.post("/diagnostics/workflow-ping/queue")
    assert res.status_code == 202
    body = res.json()
    job_id = body["job_id"]
    assert body["type"] == "workflow_ping"
    assert len(enqueued) == 1
    assert enqueued[0] == job_id
