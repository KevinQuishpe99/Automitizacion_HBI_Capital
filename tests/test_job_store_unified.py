"""JobManager y sharepoint comparten el mismo MemoryJobStore (Fase 2)."""

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.adapters.primary.http.deps import init_graph_client
from app.adapters.primary.http.routers.sharepoint import router as sharepoint_router
from app.application.job_manager import JobManager
from app.application.job_store_factory import reset_job_store_for_tests


class _MockGraph:
    async def get(self, *a, **k):
        return {}

    async def get_bytes(self, *a, **k):
        return b""

    async def put_bytes(self, *a, **k):
        return {}

    async def delete(self, *a, **k):
        return None

    async def post_json(self, *a, **k):
        return {}, 202


@pytest.fixture(autouse=True)
def _reset():
    reset_job_store_for_tests()
    yield
    reset_job_store_for_tests()


def test_sharepoint_job_visible_from_job_manager():
    app = FastAPI()
    init_graph_client(_MockGraph())
    app.include_router(sharepoint_router)
    client = TestClient(app, raise_server_exceptions=False)

    async def seed():
        jm = JobManager()
        await jm.set_job(
            "shared-job-1",
            {
                "job_id": "shared-job-1",
                "type": "notify_validar_extractos",
                "status": "completed",
                "result": {"status": "ok"},
            },
        )

    asyncio.run(seed())
    res = client.get("/graph/sharepoint/notify-validar-extractos-email/jobs/shared-job-1")
    assert res.status_code == 200
    assert res.json()["status"] == "completed"
