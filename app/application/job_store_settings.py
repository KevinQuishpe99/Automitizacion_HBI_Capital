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


def is_vercel_runtime() -> bool:
    return (os.getenv("VERCEL") or "").strip() == "1"


def has_blob_token() -> bool:
    return bool((os.getenv("BLOB_READ_WRITE_TOKEN") or "").strip())
