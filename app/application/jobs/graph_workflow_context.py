"""Inicialización de Graph para steps de workflow y fallbacks API."""

from __future__ import annotations

from typing import Any


def init_graph_for_job() -> Any:
    from app.adapters.primary.http.deps import get_graph_client, init_graph_client
    from app.adapters.secondary.ms_graph_client import MsGraphClient

    init_graph_client(MsGraphClient())
    return get_graph_client()
