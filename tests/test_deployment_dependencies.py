"""Dependencias de deploy: Vercel Services (pyproject) y Render (requirements.txt)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import index
from app.main import app as main_app


ROOT = Path(__file__).resolve().parents[1]


def test_requirements_txt_contains_fastapi() -> None:
    text = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert "fastapi" in text.lower()


def test_pyproject_toml_declares_fastapi_dependency() -> None:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "dependencies" in text
    assert "fastapi" in text.lower()


def test_import_fastapi() -> None:
    import fastapi

    assert fastapi.__version__


def test_index_imports_app() -> None:
    assert index.app is main_app


def test_health_via_index_app() -> None:
    client = TestClient(index.app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_vercel_build_check_script() -> None:
    from vercel_build_check import main

    assert main() == 0
