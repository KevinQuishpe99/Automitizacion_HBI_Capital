"""Configuración de JobStore (memoria vs Vercel Blob)."""

from __future__ import annotations

import os


def job_store_backend() -> str:
    return (os.getenv("JOB_STORE_BACKEND") or "").strip().lower()


def job_ttl_days() -> int:
    raw = (os.getenv("JOB_TTL_DAYS") or "7").strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return 7


def job_inline_result_max_bytes() -> int:
    raw = (os.getenv("JOB_INLINE_RESULT_MAX_BYTES") or "2097152").strip()
    try:
        return max(1024, int(raw))
    except ValueError:
        return 2_097_152


def default_lock_ttl_seconds() -> int:
    raw = (os.getenv("LOCK_TTL_SECONDS") or "900").strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return 900


def payment_validation_locks_enabled() -> bool:
    """
    Locks generate/finalize (mutua exclusión). Desactivados por defecto:
    la idempotencia de negocio ya protege el flujo; evita bloqueos en Blob.
  Activar con PAYMENT_VALIDATION_LOCKS_ENABLED=true cuando se quiera serializar.
    """
    raw = (os.getenv("PAYMENT_VALIDATION_LOCKS_ENABLED") or "false").strip().lower()
    return raw in ("1", "true", "yes", "on")


def is_vercel_runtime() -> bool:
    return (os.getenv("VERCEL") or "").strip() == "1"


def has_blob_token() -> bool:
    return bool((os.getenv("BLOB_READ_WRITE_TOKEN") or "").strip())
