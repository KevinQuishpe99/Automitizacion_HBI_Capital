from __future__ import annotations

from typing import Any

from fastapi import BackgroundTasks

from app.application.jobs.amortization_apply_job import execute_amortization_apply_job
from app.application.jobs.amortization_dry_run_job import execute_amortization_dry_run_job
from app.application.jobs.ensure_asientos_contables_job import execute_ensure_asientos_contables_job
from app.application.jobs.merge_composite_validado_pdfs_job import (
    execute_merge_composite_validado_pdfs_job,
)
from app.application.jobs.notify_validar_extractos_job import execute_notify_validar_extractos_job
from app.application.jobs.payment_validation_finalize_job import (
    execute_payment_validation_finalize_job,
)
from app.application.jobs.payment_validation_generate_job import (
    execute_payment_validation_generate_job,
)
from app.application.jobs.validate_payment_report_job import execute_validate_payment_report_job
from app.application.jobs.workflow_ping_job import execute_workflow_ping_job


class BackgroundJobRunner:
    """Render/local: FastAPI BackgroundTasks (comportamiento histórico)."""

    def _require_bg(self, background_tasks: BackgroundTasks | None) -> BackgroundTasks:
        if background_tasks is None:
            raise RuntimeError("BackgroundTasks es obligatorio con JOB_RUNNER_BACKEND=background")
        return background_tasks

    async def enqueue_amortization_dry_run(
        self,
        *,
        job_id: str,
        graph: Any,
        report_date_iso: str | None,
        merge_manifest_path: str | None,
        historical_file_path: str | None,
        background_tasks: BackgroundTasks | None = None,
    ) -> None:
        bg = self._require_bg(background_tasks)
        bg.add_task(
            execute_amortization_dry_run_job,
            job_id,
            graph,
            report_date_iso=report_date_iso,
            merge_manifest_path=merge_manifest_path,
            historical_file_path=historical_file_path,
        )

    async def enqueue_amortization_apply(
        self,
        *,
        job_id: str,
        graph: Any,
        report_date_iso: str | None,
        merge_manifest_path: str | None,
        historical_file_path: str | None,
        background_tasks: BackgroundTasks | None = None,
    ) -> None:
        bg = self._require_bg(background_tasks)
        bg.add_task(
            execute_amortization_apply_job,
            job_id,
            graph,
            report_date_iso=report_date_iso,
            merge_manifest_path=merge_manifest_path,
            historical_file_path=historical_file_path,
        )

    async def enqueue_validate_payment_report(
        self,
        *,
        job_id: str,
        graph: Any,
        background_tasks: BackgroundTasks | None = None,
    ) -> None:
        bg = self._require_bg(background_tasks)
        bg.add_task(execute_validate_payment_report_job, job_id, graph)

    async def enqueue_notify_validar_extractos(
        self,
        *,
        job_id: str,
        graph: Any,
        historical_file_path: str | None = None,
        to_override: str | None = None,
        cc_override: str | None = None,
        background_tasks: BackgroundTasks | None = None,
    ) -> None:
        bg = self._require_bg(background_tasks)
        bg.add_task(
            execute_notify_validar_extractos_job,
            job_id,
            graph,
            historical_file_path=historical_file_path,
            to_override=to_override,
            cc_override=cc_override,
        )

    async def enqueue_merge_composite_validado_pdfs(
        self,
        *,
        job_id: str,
        graph: Any,
        force_rebuild: bool = False,
        background_tasks: BackgroundTasks | None = None,
    ) -> None:
        bg = self._require_bg(background_tasks)
        bg.add_task(
            execute_merge_composite_validado_pdfs_job,
            job_id,
            graph,
            force_rebuild=force_rebuild,
        )

    async def enqueue_ensure_asientos_contables(
        self,
        *,
        job_id: str,
        graph: Any,
        background_tasks: BackgroundTasks | None = None,
    ) -> None:
        bg = self._require_bg(background_tasks)
        bg.add_task(execute_ensure_asientos_contables_job, job_id, graph)

    async def enqueue_payment_validation_generate(
        self,
        *,
        job_id: str,
        graph: Any,
        process_date_iso: str,
        background_tasks: BackgroundTasks | None = None,
    ) -> None:
        bg = self._require_bg(background_tasks)
        bg.add_task(
            execute_payment_validation_generate_job,
            job_id,
            graph,
            process_date_iso=process_date_iso,
        )

    async def enqueue_payment_validation_finalize(
        self,
        *,
        job_id: str,
        graph: Any,
        validation_file: str | None,
        validation_file_path: str | None,
        process_date_iso: str,
        background_tasks: BackgroundTasks | None = None,
    ) -> None:
        bg = self._require_bg(background_tasks)
        bg.add_task(
            execute_payment_validation_finalize_job,
            job_id,
            graph,
            validation_file=validation_file,
            validation_file_path=validation_file_path,
            process_date_iso=process_date_iso,
        )

    async def enqueue_workflow_ping(
        self,
        *,
        job_id: str,
        background_tasks: BackgroundTasks | None = None,
    ) -> None:
        bg = self._require_bg(background_tasks)
        bg.add_task(execute_workflow_ping_job, job_id)
