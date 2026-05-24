"""Wrapper Vercel: api/index.py reexporta la app ASGI sin duplicar lógica."""

from fastapi.testclient import TestClient

import api.index
from app.main import app as main_app


def test_vercel_api_index_exposes_app():
    assert api.index.app is main_app


def test_vercel_api_index_health():
    client = TestClient(api.index.app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
