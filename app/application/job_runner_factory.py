from __future__ import annotations

from app.adapters.secondary.background_job_runner import BackgroundJobRunner
from app.adapters.secondary.vercel_workflow_job_runner import VercelWorkflowJobRunner
from app.application.job_runner_settings import job_runner_backend, vercel_workflows_enabled
from app.domain.ports.job_runner import JobRunner

_runner: JobRunner | None = None


def get_job_runner() -> JobRunner:
    global _runner
    if _runner is not None:
        return _runner
    _runner = _resolve_job_runner()
    return _runner


def configure_job_runner(runner: JobRunner) -> None:
    global _runner
    _runner = runner


def reset_job_runner_for_tests() -> None:
    global _runner
    _runner = None


def _resolve_job_runner() -> JobRunner:
    backend = job_runner_backend()
    if backend == "vercel_workflow":
        if not vercel_workflows_enabled():
            raise RuntimeError(
                "JOB_RUNNER_BACKEND=vercel_workflow requiere VERCEL_WORKFLOWS_ENABLED=true"
            )
        return VercelWorkflowJobRunner()
    if backend != "background":
        raise RuntimeError(f"JOB_RUNNER_BACKEND desconocido: {backend!r}")
    return BackgroundJobRunner()
