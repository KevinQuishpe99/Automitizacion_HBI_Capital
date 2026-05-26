from typing import Any, Protocol, runtime_checkable

from fastapi import BackgroundTasks


@runtime_checkable
class JobRunner(Protocol):
    """Encola trabajos asíncronos (BackgroundTasks local o Vercel Workflow)."""

    async def enqueue_amortization_dry_run(
        self,
        *,
        job_id: str,
        graph: Any,
        report_date_iso: str | None,
        merge_manifest_path: str | None,
        historical_file_path: str | None,
        background_tasks: BackgroundTasks | None = None,
    ) -> None: ...

    async def enqueue_amortization_apply(
        self,
        *,
        job_id: str,
        graph: Any,
        report_date_iso: str | None,
        merge_manifest_path: str | None,
        historical_file_path: str | None,
        background_tasks: BackgroundTasks | None = None,
    ) -> None: ...
