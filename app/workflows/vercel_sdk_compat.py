"""
Compatibilidad temporal: Vercel Workflows API devuelve ``cursor`` y ``hasMore`` en
respuestas de ``events_create``, pero ``vercel==0.5.9`` valida con ``EventResult``
(extra=forbid) sin esos campos.

Aplicar al arranque del worker (``app/workflows/index.py``) antes de registrar workflows.
Eliminar cuando el paquete ``vercel`` publique un ``EventResult`` compatible.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_applied = False


def apply_vercel_workflow_event_result_compat() -> None:
    """Reemplaza ``EventResult`` por un modelo que acepta paginación de la API."""
    global _applied
    if _applied:
        return

    import pydantic
    from pydantic import Field

    from vercel._internal.workflow import world as w

    class EventResultCompat(w.BaseModel):
        model_config = pydantic.ConfigDict(extra="ignore", serialize_by_alias=True)

        event: w.Event | None = None
        events: list[w.Event] | None = None
        run: w.WorkflowRun | None = None
        step: w.WorkflowStep | None = None
        hook: Any | None = None
        wait: Any | None = None
        cursor: str | None = None
        has_more: bool | None = Field(default=None, alias="hasMore")

    w.EventResult = EventResultCompat  # type: ignore[misc, assignment]
    _applied = True
    logger.info("Vercel Workflows SDK compat applied (EventResult cursor/hasMore)")


def vercel_package_version() -> str:
    try:
        from importlib.metadata import version

        return version("vercel")
    except Exception:
        return "unknown"
