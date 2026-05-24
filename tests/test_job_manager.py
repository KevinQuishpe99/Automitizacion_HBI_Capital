import asyncio

import pytest

from app.application.job_manager import JobManager
from app.application.job_store_factory import reset_job_store_for_tests


@pytest.fixture(autouse=True)
def _reset_store():
    reset_job_store_for_tests()
    yield
    reset_job_store_for_tests()


def test_job_manager_singleton():
    manager1 = JobManager()
    manager2 = JobManager()
    assert manager1 is manager2


def test_job_manager_concurrency_lock():
    async def run_test():
        manager = JobManager()
        success1 = await manager.try_start_generate()
        assert success1 is True

        success2 = await manager.try_start_generate()
        assert success2 is False

        await manager.finish_generate()

        success3 = await manager.try_start_generate()
        assert success3 is True
        await manager.finish_generate()

    asyncio.run(run_test())


def test_job_manager_generate_blocks_finalize():
    async def run_test():
        manager = JobManager()
        assert await manager.try_start_generate() is True
        assert await manager.try_start_finalize() is False
        await manager.finish_generate()
        assert await manager.try_start_finalize() is True
        await manager.finish_finalize()

    asyncio.run(run_test())


def test_job_manager_status_updates():
    async def run_test():
        manager = JobManager()
        job_id = "test_job_123"

        await manager.set_job(job_id, {"status": "running"})
        job = await manager.get_job(job_id)
        assert job is not None
        assert job["status"] == "running"

    asyncio.run(run_test())
