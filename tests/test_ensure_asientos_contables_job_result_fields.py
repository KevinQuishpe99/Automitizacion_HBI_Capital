import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.adapters.secondary.vercel_blob_job_store import VercelBlobJobStore
from app.application.job_store_factory import (
    configure_job_store,
    reset_job_store_for_tests,
)
from app.application.jobs.ensure_asientos_contables_job import (
    execute_ensure_asientos_contables_job,
)
from app.application.use_cases.ensure_asientos_contables_folders import (
    EnsureAsientosContablesResult,
)


def test_execute_ensure_asientos_contables_job_exposes_folders_created_already_present_and_failed():
    async def run() -> None:
        store = VercelBlobJobStore.with_memory_blob()
        configure_job_store(store)

        job_id = "ens-1"
        await store.create_job(
            job_id,
            {
                "job_id": job_id,
                "type": "ensure_asientos_contables",
                "status": "queued",
            },
        )

        dummy = EnsureAsientosContablesResult(
            clients_base_path="clients",
            clients_scanned=1,
            credit_folders_scanned=2,
            folders_created=3,
            folders_already_present=5,
            subfolder_names=("ASIENTOS CONTABLES",),
            errors=[{"path": "clients/C1/CRED/x", "error": "boom"}],
        )

        with patch(
            "app.application.jobs.ensure_asientos_contables_job.ensure_asientos_contables_folders",
            new_callable=AsyncMock,
            return_value=dummy,
        ):
            await execute_ensure_asientos_contables_job(job_id, MagicMock())

        job = await store.get_job(job_id)
        assert job is not None
        assert job["status"] == "completed"
        assert job["result"]["folders_created"] == 3
        assert job["result"]["folders_already_present"] == 5
        assert job["result"]["folders_failed"] == 1

    try:
        asyncio.run(run())
    finally:
        reset_job_store_for_tests()

