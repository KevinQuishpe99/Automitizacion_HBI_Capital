from __future__ import annotations

import logging
from typing import Any

from fastapi import BackgroundTasks

from app.application.job_manager import JobManager
from app.application.job_runner_settings import (
    workflow_amortization_apply_name,
    workflow_amortization_dry_run_name,
    workflow_ensure_asientos_contables_name,
    workflow_merge_composite_validado_pdfs_name,
    workflow_notify_validar_extractos_name,
    workflow_payment_validation_finalize_name,
    workflow_payment_validation_generate_name,
    workflow_ping_name,
    workflow_validate_payment_report_name,
)
from app.application.jobs.amortization_apply_fallback import (
    execute_amortization_apply_job_with_graph,
)
from app.application.jobs.amortization_dry_run_fallback import (
    execute_amortization_dry_run_job_with_graph,
)
from app.application.jobs.ensure_asientos_contables_fallback import (
    execute_ensure_asientos_contables_job_with_graph,
)
from app.application.jobs.merge_composite_validado_pdfs_fallback import (
    execute_merge_composite_validado_pdfs_job_with_graph,
)
from app.application.jobs.notify_validar_extractos_fallback import (
    execute_notify_validar_extractos_job_with_graph,
)
from app.application.jobs.payment_validation_finalize_fallback import (
    execute_payment_validation_finalize_job_with_graph,
)
from app.application.jobs.payment_validation_generate_fallback import (
    execute_payment_validation_generate_job_with_graph,
)
from app.application.jobs.validate_payment_report_fallback import (
    execute_validate_payment_report_job_with_graph,
)
from app.application.jobs.vercel_workflow_fallback import schedule_workflow_api_fallback
from app.application.jobs.workflow_ping_job import execute_workflow_ping_job

logger = logging.getLogger(__name__)


class VercelWorkflowJobRunner:
    """Vercel Pro: encola jobs vía ``vercel.workflow.start`` + fallback API si el worker no avanza."""

    async def _start_workflow(
        self,
        *,
        workflow_fn: Any,
        job_id: str,
        workflow_name: str,
        kwargs: dict[str, Any],
        extra_job_updates: dict[str, Any] | None = None,
    ) -> None:
        try:
            from vercel.workflow import start
        except ImportError as exc:
            raise RuntimeError(
                "JOB_RUNNER_BACKEND=vercel_workflow requiere el paquete 'vercel' "
                "(pip install vercel>=0.5.2)"
            ) from exc

        logger.info(
            "workflow.start before job_id=%s workflow_name=%s",
            job_id,
            workflow_name,
        )
        run = await start(workflow_fn, job_id=job_id, **kwargs)
        logger.info(
            "workflow.start after job_id=%s workflow_name=%s workflow_run_id=%s",
            job_id,
            workflow_name,
            run.run_id,
        )
        now = _utc_now_iso()
        updates: dict[str, Any] = {
            "workflow_run_id": run.run_id,
            "workflow_name": workflow_name,
            "status": "running",
            "started_at": now,
            "execution_phase": "workflow_dispatched",
            "updated_at": now,
        }
        if extra_job_updates:
            updates.update(extra_job_updates)
        jm = JobManager()
        await jm.set_job(job_id, updates)

    async def enqueue_workflow_ping(
        self,
        *,
        job_id: str,
        background_tasks: BackgroundTasks | None = None,
    ) -> None:
        from app.workflows.workflow_ping_workflow import workflow_ping_workflow

        await self._start_workflow(
            workflow_fn=workflow_ping_workflow,
            job_id=job_id,
            workflow_name=workflow_ping_name(),
            kwargs={},
            extra_job_updates={"type": "workflow_ping"},
        )
        schedule_workflow_api_fallback(
            background_tasks,
            job_id=job_id,
            label="workflow_ping",
            execute=lambda: execute_workflow_ping_job(job_id),
        )

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
        del graph
        from app.workflows.amortization_dry_run_workflow import amortization_dry_run_workflow

        await self._start_workflow(
            workflow_fn=amortization_dry_run_workflow,
            job_id=job_id,
            workflow_name=workflow_amortization_dry_run_name(),
            kwargs={
                "report_date_iso": report_date_iso,
                "merge_manifest_path": merge_manifest_path,
                "historical_file_path": historical_file_path,
            },
        )
        schedule_workflow_api_fallback(
            background_tasks,
            job_id=job_id,
            label="amortization_dry_run",
            execute=lambda: execute_amortization_dry_run_job_with_graph(
                job_id,
                report_date_iso=report_date_iso,
                merge_manifest_path=merge_manifest_path,
                historical_file_path=historical_file_path,
            ),
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
        del graph
        from app.workflows.amortization_apply_workflow import amortization_apply_workflow

        await self._start_workflow(
            workflow_fn=amortization_apply_workflow,
            job_id=job_id,
            workflow_name=workflow_amortization_apply_name(),
            kwargs={
                "report_date_iso": report_date_iso,
                "merge_manifest_path": merge_manifest_path,
                "historical_file_path": historical_file_path,
            },
            extra_job_updates={"type": "amortization_apply"},
        )
        schedule_workflow_api_fallback(
            background_tasks,
            job_id=job_id,
            label="amortization_apply",
            execute=lambda: execute_amortization_apply_job_with_graph(
                job_id,
                report_date_iso=report_date_iso,
                merge_manifest_path=merge_manifest_path,
                historical_file_path=historical_file_path,
            ),
        )

    async def enqueue_validate_payment_report(
        self,
        *,
        job_id: str,
        graph: Any,
        background_tasks: BackgroundTasks | None = None,
    ) -> None:
        del graph
        from app.workflows.validate_payment_report_workflow import (
            validate_payment_report_workflow,
        )

        await self._start_workflow(
            workflow_fn=validate_payment_report_workflow,
            job_id=job_id,
            workflow_name=workflow_validate_payment_report_name(),
            kwargs={},
        )
        schedule_workflow_api_fallback(
            background_tasks,
            job_id=job_id,
            label="validate_payment_report",
            execute=lambda: execute_validate_payment_report_job_with_graph(job_id),
        )

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
        del graph
        from app.workflows.notify_validar_extractos_workflow import (
            notify_validar_extractos_workflow,
        )

        await self._start_workflow(
            workflow_fn=notify_validar_extractos_workflow,
            job_id=job_id,
            workflow_name=workflow_notify_validar_extractos_name(),
            kwargs={
                "historical_file_path": historical_file_path,
                "to_override": to_override,
                "cc_override": cc_override,
            },
            extra_job_updates={"type": "notify_validar_extractos"},
        )
        schedule_workflow_api_fallback(
            background_tasks,
            job_id=job_id,
            label="notify_validar_extractos",
            execute=lambda: execute_notify_validar_extractos_job_with_graph(
                job_id,
                historical_file_path=historical_file_path,
                to_override=to_override,
                cc_override=cc_override,
            ),
        )

    async def enqueue_merge_composite_validado_pdfs(
        self,
        *,
        job_id: str,
        graph: Any,
        force_rebuild: bool = False,
        background_tasks: BackgroundTasks | None = None,
    ) -> None:
        del graph
        from app.workflows.merge_composite_validado_pdfs_workflow import (
            merge_composite_validado_pdfs_workflow,
        )

        await self._start_workflow(
            workflow_fn=merge_composite_validado_pdfs_workflow,
            job_id=job_id,
            workflow_name=workflow_merge_composite_validado_pdfs_name(),
            kwargs={"force_rebuild": force_rebuild},
            extra_job_updates={"type": "merge_composite_validado_pdfs"},
        )
        schedule_workflow_api_fallback(
            background_tasks,
            job_id=job_id,
            label="merge_composite_validado_pdfs",
            execute=lambda: execute_merge_composite_validado_pdfs_job_with_graph(
                job_id, force_rebuild=force_rebuild
            ),
        )

    async def enqueue_ensure_asientos_contables(
        self,
        *,
        job_id: str,
        graph: Any,
        background_tasks: BackgroundTasks | None = None,
    ) -> None:
        del graph
        from app.workflows.ensure_asientos_contables_workflow import (
            ensure_asientos_contables_workflow,
        )

        await self._start_workflow(
            workflow_fn=ensure_asientos_contables_workflow,
            job_id=job_id,
            workflow_name=workflow_ensure_asientos_contables_name(),
            kwargs={},
            extra_job_updates={"type": "ensure_asientos_contables"},
        )
        schedule_workflow_api_fallback(
            background_tasks,
            job_id=job_id,
            label="ensure_asientos_contables",
            execute=lambda: execute_ensure_asientos_contables_job_with_graph(job_id),
        )

    async def enqueue_payment_validation_generate(
        self,
        *,
        job_id: str,
        graph: Any,
        process_date_iso: str,
        background_tasks: BackgroundTasks | None = None,
    ) -> None:
        del graph
        from app.workflows.payment_validation_generate_workflow import (
            payment_validation_generate_workflow,
        )

        await self._start_workflow(
            workflow_fn=payment_validation_generate_workflow,
            job_id=job_id,
            workflow_name=workflow_payment_validation_generate_name(),
            kwargs={"process_date_iso": process_date_iso},
            extra_job_updates={"type": "generate"},
        )
        schedule_workflow_api_fallback(
            background_tasks,
            job_id=job_id,
            label="generate",
            execute=lambda: execute_payment_validation_generate_job_with_graph(
                job_id, process_date_iso=process_date_iso
            ),
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
        del graph
        from app.workflows.payment_validation_finalize_workflow import (
            payment_validation_finalize_workflow,
        )

        await self._start_workflow(
            workflow_fn=payment_validation_finalize_workflow,
            job_id=job_id,
            workflow_name=workflow_payment_validation_finalize_name(),
            kwargs={
                "validation_file": validation_file,
                "validation_file_path": validation_file_path,
                "process_date_iso": process_date_iso,
            },
            extra_job_updates={"type": "finalize"},
        )
        schedule_workflow_api_fallback(
            background_tasks,
            job_id=job_id,
            label="finalize",
            execute=lambda: execute_payment_validation_finalize_job_with_graph(
                job_id,
                validation_file=validation_file,
                validation_file_path=validation_file_path,
                process_date_iso=process_date_iso,
            ),
        )


def _utc_now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
