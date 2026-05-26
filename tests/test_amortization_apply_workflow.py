"""Amortization apply: Vercel Workflow, job executor y router."""

from __future__ import annotations

import asyncio
import importlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.adapters.primary.http.deps import init_graph_client
from app.adapters.primary.http.routers.payment_validation import router
from app.adapters.secondary.background_job_runner import BackgroundJobRunner
from app.adapters.secondary.vercel_blob_job_store import VercelBlobJobStore
from app.application import job_runner_factory
from app.application.job_manager import JobManager
from app.application.job_store_factory import configure_job_store, reset_job_store_for_tests
from app.application.jobs.amortization_apply_job import execute_amortization_apply_job
from app.application.services.accounting_pdf_parser import (
    ACCOUNT_CAPITAL,
    ACCOUNT_SALDOS_MENORES,
    WARNING_BANK_INFERRED,
)
from app.application.services.amortization_apply_safety import item_warnings_allowed
from app.application.use_cases.amortization_fill_apply import (
    AmortizationPreflightError,
    validate_amortization_preflight,
)
from app.workflows.wf import wf


class MockGraphClient:
    async def get(self, endpoint, params=None):
        return {"value": [{"id": "site"}, {"id": "drive", "name": "Doc"}]}

    async def get_bytes(self, *args, **kwargs):
        return b""

    async def put_bytes(self, *args, **kwargs):
        return {"id": "x"}


def build_app() -> FastAPI:
    app = FastAPI()
    init_graph_client(MockGraphClient())
    app.include_router(router)
    return app


@pytest.fixture(autouse=True)
def _reset() -> None:
    reset_job_store_for_tests()
    job_runner_factory.reset_job_runner_for_tests()
    yield
    reset_job_store_for_tests()
    job_runner_factory.reset_job_runner_for_tests()


@pytest.fixture
def client() -> TestClient:
    return TestClient(build_app(), raise_server_exceptions=False)


def test_workflow_entrypoint_registers_apply_workflow() -> None:
    index = importlib.import_module("app.workflows.index")
    assert hasattr(index, "_amortization_apply_workflow")
    from app.workflows.amortization_apply_workflow import (
        amortization_apply_step,
        amortization_apply_workflow,
    )

    registered = list(wf._workflows.keys())
    step_keys = list(wf._steps.keys())
    assert any("amortization_apply_workflow" in key for key in registered)
    assert any("amortization_apply_step" in key for key in step_keys)
    assert amortization_apply_workflow is not None
    assert amortization_apply_step is not None


def test_execute_amortization_apply_job_queued_to_completed() -> None:
    async def run() -> None:
        store = VercelBlobJobStore.with_memory_blob()
        configure_job_store(store)
        await store.create_job(
            "apply-1",
            {"job_id": "apply-1", "type": "amortization_apply", "status": "queued"},
        )

        async def fake_apply(graph, **kwargs):
            return {"status": "ok", "mode": "apply", "summary": {"applied": 1}}

        with patch(
            "app.application.jobs.amortization_apply_job.run_amortization_fill_apply",
            new_callable=AsyncMock,
            side_effect=fake_apply,
        ):
            await execute_amortization_apply_job(
                "apply-1",
                MockGraphClient(),
                report_date_iso="2026-05-15",
                merge_manifest_path=None,
                historical_file_path=None,
            )

        job = await store.get_job("apply-1")
        assert job is not None
        assert job["status"] == "completed"
        assert job["result"]["status"] == "ok"

    asyncio.run(run())


def test_execute_amortization_apply_job_marks_failed_on_exception() -> None:
    async def run() -> None:
        store = VercelBlobJobStore.with_memory_blob()
        configure_job_store(store)
        await store.create_job(
            "apply-fail",
            {"job_id": "apply-fail", "type": "amortization_apply", "status": "queued"},
        )

        with patch(
            "app.application.jobs.amortization_apply_job.run_amortization_fill_apply",
            new_callable=AsyncMock,
            side_effect=ValueError("merge_manifest_not_found|path"),
        ):
            await execute_amortization_apply_job(
                "apply-fail",
                MockGraphClient(),
                report_date_iso="2026-05-15",
                merge_manifest_path=None,
                historical_file_path=None,
            )

        job = await store.get_job("apply-fail")
        assert job is not None
        assert job["status"] == "failed"
        assert job["error"]["error_code"] == "merge_manifest_not_found"

    asyncio.run(run())


def test_preflight_blocks_errors() -> None:
    dry = {"summary": {"errors": 1, "revision_manual": 0}, "items": []}
    with pytest.raises(AmortizationPreflightError) as exc:
        validate_amortization_preflight(dry)
    assert exc.value.error_code == "preflight_errors"


def test_bank_warning_allowed_under_safe_rule() -> None:
    item = {
        "warnings": [WARNING_BANK_INFERRED],
        "detected_codes": [ACCOUNT_SALDOS_MENORES, ACCOUNT_CAPITAL],
        "payment_application": {
            "valor_pagado_cliente": 100.0,
            "saldos_menores": 100.0,
            "capital": 100.0,
        },
    }
    assert item_warnings_allowed(item) is True


def test_vercel_runner_starts_apply_workflow() -> None:
    async def run() -> None:
        from app.adapters.secondary.vercel_workflow_job_runner import VercelWorkflowJobRunner

        store = VercelBlobJobStore.with_memory_blob()
        configure_job_store(store)
        await store.create_job(
            "apply-2",
            {"job_id": "apply-2", "type": "amortization_apply", "status": "queued"},
        )

        run_mock = MagicMock(run_id="wrun_apply_001")
        with patch("vercel.workflow.start", new_callable=AsyncMock, return_value=run_mock):
            runner = VercelWorkflowJobRunner()
            await runner.enqueue_amortization_apply(
                job_id="apply-2",
                graph=MockGraphClient(),
                report_date_iso="2026-05-15",
                merge_manifest_path=None,
                historical_file_path=None,
            )

        job = await store.get_job("apply-2")
        assert job is not None
        assert job["workflow_run_id"] == "wrun_apply_001"
        assert job["workflow_name"] == "amortization_apply_workflow"

    asyncio.run(run())


def test_vercel_runner_starts_decorated_apply_workflow() -> None:
    async def run() -> None:
        from app.adapters.secondary.vercel_workflow_job_runner import VercelWorkflowJobRunner
        from app.workflows.amortization_apply_workflow import amortization_apply_workflow

        captured: dict = {}

        async def fake_start(fn, job_id: str, **kwargs):
            captured["fn"] = fn
            captured["job_id"] = job_id
            captured["kwargs"] = kwargs
            return MagicMock(run_id="wrun_ref_apply")

        with patch("vercel.workflow.start", new_callable=AsyncMock, side_effect=fake_start):
            runner = VercelWorkflowJobRunner()
            await runner.enqueue_amortization_apply(
                job_id="apply-ref",
                graph=MockGraphClient(),
                report_date_iso="2026-05-15",
                merge_manifest_path="LOGS/x.json",
                historical_file_path=None,
            )

        assert captured["fn"] is amortization_apply_workflow
        assert captured["job_id"] == "apply-ref"
        assert captured["kwargs"]["report_date_iso"] == "2026-05-15"

    asyncio.run(run())


def test_apply_queue_uses_background_runner_by_default(client: TestClient) -> None:
    assert isinstance(job_runner_factory.get_job_runner(), BackgroundJobRunner)


def test_apply_queue_workflow_mode_enqueues_without_inline_execute(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    enqueued: list[dict] = []

    class _WorkflowRunner:
        async def enqueue_amortization_apply(self, **kwargs):
            enqueued.append(kwargs)

    monkeypatch.setenv("JOB_RUNNER_BACKEND", "vercel_workflow")
    monkeypatch.setenv("VERCEL_WORKFLOWS_ENABLED", "true")
    job_runner_factory.reset_job_runner_for_tests()
    job_runner_factory.configure_job_runner(_WorkflowRunner())  # type: ignore[arg-type]

    res = client.post(
        "/graph/sharepoint/payment-validation/amortization/apply/queue",
        json={"report_date_iso": "2026-05-15"},
    )
    assert res.status_code == 202
    body = res.json()
    assert body["status"] == "queued"
    assert len(enqueued) == 1
    assert enqueued[0]["job_id"] == body["job_id"]

    async def _assert_still_queued() -> None:
        job = await JobManager().get_job(body["job_id"])
        assert job is not None
        assert job["status"] == "queued"

    asyncio.run(_assert_still_queued())

