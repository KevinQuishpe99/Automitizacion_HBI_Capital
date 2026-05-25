"""
Entrypoint único del worker Vercel Workflows.

Importar todos los módulos con ``@wf.workflow`` para que el runtime los registre.
"""

from __future__ import annotations

# noqa: F401 — side effect: register workflows on shared ``wf``
from app.workflows import amortization_dry_run_workflow as _amortization_dry_run_workflow
from app.workflows import workflow_ping_workflow as _workflow_ping_workflow

__all__ = [
    "_amortization_dry_run_workflow",
    "_workflow_ping_workflow",
]
