"""
Entrypoint único del worker Vercel Workflows.

Importar todos los módulos con ``@wf.workflow`` para que el runtime los registre.
"""

from __future__ import annotations

print("WORKFLOW_ENTRYPOINT_LOADED", flush=True)

from app.workflows.vercel_sdk_compat import apply_vercel_workflow_event_result_compat

apply_vercel_workflow_event_result_compat()

# noqa: F401 — side effect: register workflows on shared ``wf``
from app.workflows import amortization_dry_run_workflow as _amortization_dry_run_workflow

print("AMORTIZATION_DRY_RUN_IMPORTED", flush=True)

from app.workflows import workflow_ping_workflow as _workflow_ping_workflow

from app.workflows import amortization_apply_workflow as _amortization_apply_workflow

print("AMORTIZATION_APPLY_WORKFLOW_REGISTERED", flush=True)

__all__ = [
    "_amortization_dry_run_workflow",
    "_amortization_apply_workflow",
    "_workflow_ping_workflow",
]
