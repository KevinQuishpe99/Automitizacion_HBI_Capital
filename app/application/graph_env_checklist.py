"""Comprobación segura de variables GRAPH_* (solo presencia, sin valores)."""

from __future__ import annotations

import os

# Obligatorias para casi todos los flujos PA
_GRAPH_CORE = (
    "GRAPH_TENANT_ID",
    "GRAPH_CLIENT_ID",
    "GRAPH_CLIENT_SECRET",
    "GRAPH_SHAREPOINT_SITE_SEARCH",
)

# Ruta principal: se permite fallback a archivo banco
_GRAPH_CORE_PATH = (
    "GRAPH_SHAREPOINT_FILE_PATH",
    "GRAPH_BANK_PAYMENTS_FILE_PATH",
)

# Opcional: si falta, se usa primer drive disponible
_GRAPH_OPTIONAL_CORE = (
    "GRAPH_SHAREPOINT_DRIVE_NAME",
)

# Generate / finalize
_GRAPH_PAYMENT_VALIDATION = (
    "GRAPH_BANK_PAYMENTS_FILE_PATH",
    "GRAPH_CLIENTS_BASE_PATH",
    "GRAPH_PAYMENT_VALIDATION_REVIEW_PATH",
    "GRAPH_PAYMENT_VALIDATION_HISTORY_PATH",
    "GRAPH_VALIDATION_FILE_PREFIX",
)

# Merge / notify / amortization
_GRAPH_OPERATIONS = (
    "GRAPH_PAYMENT_VALIDATION_CONTROL_PATH",
    "GRAPH_PAYMENT_VALIDATION_LOGS_PATH",
    "GRAPH_MERGE_CONTROL_WORKBOOK_PATH",
    "GRAPH_VALIDAR_EXTRACTO_ESTADO_CONTAINS",
    "GRAPH_VALIDAR_NOTIFY_CORREOS_XLSX_PATH",
)

_GRAPH_MAIL = (
    "GRAPH_MAIL_SENDER_EMAIL",
    "GRAPH_MAIL_TO",
)


def graph_env_presence() -> dict[str, bool]:
    """True si la variable tiene valor no vacío."""
    all_keys = _GRAPH_CORE + _GRAPH_CORE_PATH + _GRAPH_OPTIONAL_CORE + _GRAPH_PAYMENT_VALIDATION + _GRAPH_OPERATIONS + _GRAPH_MAIL
    return {key: bool((os.getenv(key) or "").strip()) for key in all_keys}


def graph_env_missing_required() -> list[str]:
    """Variables del núcleo PA que faltan en el runtime."""
    presence = graph_env_presence()
    missing = [k for k in _GRAPH_CORE if not presence.get(k)]
    if not (presence.get("GRAPH_SHAREPOINT_FILE_PATH") or presence.get("GRAPH_BANK_PAYMENTS_FILE_PATH")):
        missing.append("GRAPH_SHAREPOINT_FILE_PATH (or GRAPH_BANK_PAYMENTS_FILE_PATH)")
    return missing
