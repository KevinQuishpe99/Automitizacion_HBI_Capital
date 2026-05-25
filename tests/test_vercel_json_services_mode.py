"""Validación de vercel.json para Vercel Services mode (FastAPI + Workflows)."""

from __future__ import annotations

import json
from pathlib import Path


def _load_vercel_config() -> dict:
    path = Path(__file__).resolve().parents[1] / "vercel.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_vercel_json_services_mode_structure() -> None:
    config = _load_vercel_config()

    assert "functions" not in config
    assert config.get("framework") == "services"
    assert "experimentalServices" in config

    services = config["experimentalServices"]
    assert "api" in services
    assert "amortization_dry_run" in services

    api = services["api"]
    assert api["framework"] == "fastapi"
    assert api["entrypoint"] == "index.py"
    assert api["routePrefix"] == "/"
    assert api["maxDuration"] == 60
    assert api["memory"] == 2048

    worker = services["amortization_dry_run"]
    assert worker["type"] == "worker"
    assert worker["entrypoint"] == "app/workflows/amortization_dry_run_workflow.py"
    assert worker["topics"] == ["__wkf_*"]


def test_vercel_json_no_functions_services_conflict() -> None:
    config = _load_vercel_config()
    assert not (config.get("functions") and config.get("experimentalServices"))
