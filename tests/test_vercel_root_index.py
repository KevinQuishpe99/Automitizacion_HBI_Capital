"""Entrypoint root Vercel: index.py reexporta la app ASGI sin duplicar lógica."""

from fastapi.testclient import TestClient

import index
from app.main import app as main_app


def test_vercel_root_index_exposes_app():
    assert index.app is main_app


def test_vercel_root_index_health():
    client = TestClient(index.app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
