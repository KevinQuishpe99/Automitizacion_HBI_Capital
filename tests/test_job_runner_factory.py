"""Factory y modos de JobRunner."""

import pytest

from app.adapters.secondary.background_job_runner import BackgroundJobRunner
from app.application import job_runner_factory
from app.application.job_runner_settings import job_runner_backend


@pytest.fixture(autouse=True)
def _reset_runner():
    job_runner_factory.reset_job_runner_for_tests()
    yield
    job_runner_factory.reset_job_runner_for_tests()


def test_factory_defaults_to_background(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JOB_RUNNER_BACKEND", raising=False)
    monkeypatch.delenv("VERCEL_WORKFLOWS_ENABLED", raising=False)
    runner = job_runner_factory.get_job_runner()
    assert isinstance(runner, BackgroundJobRunner)
    assert job_runner_backend() == "background"


def test_factory_vercel_workflow_requires_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JOB_RUNNER_BACKEND", "vercel_workflow")
    monkeypatch.setenv("VERCEL_WORKFLOWS_ENABLED", "false")
    with pytest.raises(RuntimeError, match="VERCEL_WORKFLOWS_ENABLED"):
        job_runner_factory.get_job_runner()


def test_factory_vercel_workflow_with_mock_runner(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JOB_RUNNER_BACKEND", "vercel_workflow")
    monkeypatch.setenv("VERCEL_WORKFLOWS_ENABLED", "true")

    class _Stub:
        pass

    stub = _Stub()
    job_runner_factory.configure_job_runner(stub)  # type: ignore[arg-type]
    assert job_runner_factory.get_job_runner() is stub
