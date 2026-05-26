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

    async def enqueue_validate_payment_report(
        self,
        *,
        job_id: str,
        graph: Any,
        background_tasks: BackgroundTasks | None = None,
    ) -> None: ...

    async def enqueue_notify_validar_extractos(
        self,
        *,
        job_id: str,
        graph: Any,
        historical_file_path: str | None = None,
        to_override: str | None = None,
        cc_override: str | None = None,
        background_tasks: BackgroundTasks | None = None,
    ) -> None: ...

    async def enqueue_merge_composite_validado_pdfs(
        self,
        *,
        job_id: str,
        graph: Any,
        force_rebuild: bool = False,
        background_tasks: BackgroundTasks | None = None,
    ) -> None: ...

    async def enqueue_ensure_asientos_contables(
        self,
        *,
        job_id: str,
        graph: Any,
        background_tasks: BackgroundTasks | None = None,
    ) -> None: ...

    async def enqueue_payment_validation_generate(
        self,
        *,
        job_id: str,
        graph: Any,
        process_date_iso: str,
        background_tasks: BackgroundTasks | None = None,
    ) -> None: ...

    async def enqueue_payment_validation_finalize(
        self,
        *,
        job_id: str,
        graph: Any,
        validation_file: str | None,
        validation_file_path: str | None,
        process_date_iso: str,
        background_tasks: BackgroundTasks | None = None,
    ) -> None: ...

    async def enqueue_workflow_ping(
        self,
        *,
        job_id: str,
        background_tasks: BackgroundTasks | None = None,
    ) -> None: ...
