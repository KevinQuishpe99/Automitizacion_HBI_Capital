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
from app.workflows import amortization_apply_workflow as _amortization_apply_workflow
from app.workflows import workflow_ping_workflow as _workflow_ping_workflow
from app.workflows import validate_payment_report_workflow as _validate_payment_report_workflow
from app.workflows import notify_validar_extractos_workflow as _notify_validar_extractos_workflow
from app.workflows import merge_composite_validado_pdfs_workflow as _merge_composite_validado_pdfs_workflow
from app.workflows import ensure_asientos_contables_workflow as _ensure_asientos_contables_workflow
from app.workflows import payment_validation_generate_workflow as _payment_validation_generate_workflow
from app.workflows import payment_validation_finalize_workflow as _payment_validation_finalize_workflow

__all__ = [
    "_amortization_dry_run_workflow",
    "_amortization_apply_workflow",
    "_workflow_ping_workflow",
    "_validate_payment_report_workflow",
    "_notify_validar_extractos_workflow",
    "_merge_composite_validado_pdfs_workflow",
    "_ensure_asientos_contables_workflow",
    "_payment_validation_generate_workflow",
    "_payment_validation_finalize_workflow",
]
