"""Configuración del backend de ejecución de jobs (background vs Vercel Workflow)."""

from __future__ import annotations

import os


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in ("1", "true", "yes", "on")


def job_runner_backend() -> str:
    """
    ``background`` (default) | ``vercel_workflow``.

    Local/Render: omitir o ``background``.
    Vercel (dry-run workflow): ``vercel_workflow`` + ``VERCEL_WORKFLOWS_ENABLED=true``.
    Solo afecta ``POST .../amortization/dry-run/queue``; generate/finalize/apply usan BackgroundTasks.
    """
    explicit = (os.getenv("JOB_RUNNER_BACKEND") or "").strip().lower()
    if explicit in ("background", "vercel_workflow"):
        return explicit
    return "background"


def vercel_workflows_enabled() -> bool:
    return _truthy(os.getenv("VERCEL_WORKFLOWS_ENABLED"))


def workflow_amortization_dry_run_name() -> str:
    return (
        (os.getenv("WORKFLOW_AMORTIZATION_DRY_RUN_NAME") or "").strip()
        or "amortization_dry_run_workflow"
    )


def workflow_ping_name() -> str:
    return (os.getenv("WORKFLOW_PING_NAME") or "").strip() or "workflow_ping_workflow"


def is_vercel_runtime() -> bool:
    return (os.getenv("VERCEL") or "").strip() == "1"


def use_vercel_workflow_runner() -> bool:
    return job_runner_backend() == "vercel_workflow" and vercel_workflows_enabled()
