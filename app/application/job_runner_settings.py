"""Configuración del backend de ejecución de jobs (background vs Vercel Workflow)."""

from __future__ import annotations

import os


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in ("1", "true", "yes", "on")


def _workflow_name(env_key: str, default: str) -> str:
    return (os.getenv(env_key) or "").strip() or default


def job_runner_backend() -> str:
    """
    ``background`` (default) | ``vercel_workflow``.

    Local/Render: omitir o ``background``.
    Vercel: ``vercel_workflow`` + ``VERCEL_WORKFLOWS_ENABLED=true``.
    Todos los endpoints /queue pesados usan ``get_job_runner()``.
    """
    explicit = (os.getenv("JOB_RUNNER_BACKEND") or "").strip().lower()
    if explicit in ("background", "vercel_workflow"):
        return explicit
    return "background"


def vercel_workflows_enabled() -> bool:
    return _truthy(os.getenv("VERCEL_WORKFLOWS_ENABLED"))


def workflow_amortization_dry_run_name() -> str:
    return _workflow_name(
        "WORKFLOW_AMORTIZATION_DRY_RUN_NAME", "amortization_dry_run_workflow"
    )


def workflow_ping_name() -> str:
    return _workflow_name("WORKFLOW_PING_NAME", "workflow_ping_workflow")


def workflow_amortization_apply_name() -> str:
    return _workflow_name(
        "WORKFLOW_AMORTIZATION_APPLY_NAME", "amortization_apply_workflow"
    )


def workflow_validate_payment_report_name() -> str:
    return _workflow_name(
        "WORKFLOW_VALIDATE_PAYMENT_REPORT_NAME", "validate_payment_report_workflow"
    )


def workflow_notify_validar_extractos_name() -> str:
    return _workflow_name(
        "WORKFLOW_NOTIFY_VALIDAR_EXTRACTOS_NAME", "notify_validar_extractos_workflow"
    )


def workflow_merge_composite_validado_pdfs_name() -> str:
    return _workflow_name(
        "WORKFLOW_MERGE_COMPOSITE_VALIDADO_PDFS_NAME",
        "merge_composite_validado_pdfs_workflow",
    )


def workflow_ensure_asientos_contables_name() -> str:
    return _workflow_name(
        "WORKFLOW_ENSURE_ASIENTOS_CONTABLES_NAME",
        "ensure_asientos_contables_workflow",
    )


def workflow_payment_validation_generate_name() -> str:
    return _workflow_name(
        "WORKFLOW_PAYMENT_VALIDATION_GENERATE_NAME",
        "payment_validation_generate_workflow",
    )


def workflow_payment_validation_finalize_name() -> str:
    return _workflow_name(
        "WORKFLOW_PAYMENT_VALIDATION_FINALIZE_NAME",
        "payment_validation_finalize_workflow",
    )


def is_vercel_runtime() -> bool:
    return (os.getenv("VERCEL") or "").strip() == "1"


def use_vercel_workflow_runner() -> bool:
    return job_runner_backend() == "vercel_workflow" and vercel_workflows_enabled()
