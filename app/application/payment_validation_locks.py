"""Estado, diagnóstico y liberación de locks generate/finalize (Blob compartido Render + Vercel)."""

from __future__ import annotations

import logging
from typing import Any

from app.application.job_store_factory import (
    _LOCK_FINALIZE,
    _LOCK_GENERATE,
    _LOCK_HOLDER,
    get_job_store,
    lock_ttl_seconds,
)
from app.application.lock_utils import (
    is_legacy_oversized_lock,
    is_lock_expired,
    lock_granted_ttl_seconds,
    seconds_until_expiry,
    should_relinquish_lock,
)

logger = logging.getLogger(__name__)


async def _lock_record(key: str) -> dict[str, Any] | None:
    store = get_job_store()
    get_lock = getattr(store, "get_lock", None)
    if callable(get_lock):
        return await get_lock(key)
    if await store.is_lock_held(key):
        return {"lock_key": key, "holder": _LOCK_HOLDER, "expires_at": None}
    return None


def _lock_view(key: str, record: dict[str, Any] | None) -> dict[str, Any]:
    if record is None:
        return {
            "lock_key": key,
            "held": False,
            "holder": None,
            "created_at": None,
            "expires_at": None,
            "expired": False,
            "seconds_until_expiry": None,
        }
    expires_at = record.get("expires_at")
    ttl = lock_ttl_seconds()
    expired = is_lock_expired(expires_at)
    legacy_stale = is_legacy_oversized_lock(record, configured_ttl_seconds=ttl)
    relinquish = should_relinquish_lock(record, configured_ttl_seconds=ttl)
    held = not relinquish and bool(record.get("holder"))
    return {
        "lock_key": key,
        "held": held,
        "holder": record.get("holder"),
        "created_at": record.get("created_at"),
        "expires_at": expires_at,
        "expired": expired,
        "legacy_ttl_exceeded": legacy_stale,
        "granted_ttl_seconds": lock_granted_ttl_seconds(
            created_at=record.get("created_at"),
            expires_at=expires_at,
        ),
        "configured_ttl_seconds": ttl,
        "seconds_until_expiry": seconds_until_expiry(expires_at),
    }


async def lock_status() -> dict[str, bool | str | int]:
    """Compatibilidad con respuestas 409 existentes."""
    detailed = await detailed_lock_status()
    gen = detailed["generate"]
    fin = detailed["finalize"]
    return {
        "generate_lock_held": bool(gen.get("held")),
        "finalize_lock_held": bool(fin.get("held")),
        "lock_holder": _LOCK_HOLDER,
        "generate_lock_key": _LOCK_GENERATE,
        "finalize_lock_key": _LOCK_FINALIZE,
        "lock_ttl_seconds": lock_ttl_seconds(),
    }


async def detailed_lock_status() -> dict[str, Any]:
    from app.application.job_store_settings import payment_validation_locks_enabled

    gen_rec = await _lock_record(_LOCK_GENERATE)
    fin_rec = await _lock_record(_LOCK_FINALIZE)
    return {
        "locks_enabled": payment_validation_locks_enabled(),
        "lock_ttl_seconds": lock_ttl_seconds(),
        "lock_holder": _LOCK_HOLDER,
        "generate": _lock_view(_LOCK_GENERATE, gen_rec),
        "finalize": _lock_view(_LOCK_FINALIZE, fin_rec),
    }


async def cleanup_expired_payment_validation_locks() -> dict[str, Any]:
    """Elimina locks expirados o legacy (TTL emitido > LOCK_TTL_SECONDS actual)."""
    store = get_job_store()
    ttl = lock_ttl_seconds()
    cleaned: list[str] = []
    reasons: dict[str, str] = {}
    for key in (_LOCK_GENERATE, _LOCK_FINALIZE):
        rec = await _lock_record(key)
        if not rec or not should_relinquish_lock(rec, configured_ttl_seconds=ttl):
            continue
        if is_lock_expired(rec.get("expires_at")):
            reasons[key] = "expired"
        else:
            reasons[key] = "legacy_ttl_exceeded"
        cleanup = getattr(store, "cleanup_expired_lock", None)
        if callable(cleanup):
            if await cleanup(key):
                cleaned.append(key)
                continue
        await store.release_lock(key, str(rec.get("holder") or _LOCK_HOLDER))
        cleaned.append(key)
    return {
        "cleaned": cleaned,
        "reasons": reasons,
        "locks": await detailed_lock_status(),
    }


async def release_all_payment_validation_locks() -> dict[str, bool | str]:
    store = get_job_store()
    await store.release_lock(_LOCK_GENERATE, _LOCK_HOLDER)
    await store.release_lock(_LOCK_FINALIZE, _LOCK_HOLDER)
    from app.application.job_manager import JobManager

    jm = JobManager()
    jm._generate_active = False
    jm._finalize_active = False
    return await lock_status()


async def release_stale_lock_admin(*, lock_key: str, confirm: bool) -> dict[str, Any]:
    if not confirm:
        return {"released": False, "reason": "confirm_required"}
    if lock_key not in (_LOCK_GENERATE, _LOCK_FINALIZE):
        return {"released": False, "reason": "invalid_lock_key"}
    store = get_job_store()
    before = _lock_view(lock_key, await _lock_record(lock_key))
    await store.release_lock(lock_key, _LOCK_HOLDER)
    from app.application.job_manager import JobManager

    jm = JobManager()
    if lock_key == _LOCK_GENERATE:
        jm._generate_active = False
    else:
        jm._finalize_active = False
    logger.warning(
        "payment_validation lock force-released via diagnostics lock_key=%s prior_held=%s",
        lock_key,
        before.get("held"),
    )
    return {
        "released": True,
        "lock_key": lock_key,
        "before": before,
        "locks": await detailed_lock_status(),
    }


async def build_lock_conflict_detail(*, operation: str) -> dict[str, Any]:
    """Payload enriquecido para HTTP 409 (sin secretos)."""
    locks = await detailed_lock_status()
    return {
        "error": "generate_or_finalize_lock_active",
        "operation": operation,
        "user_message": (
            "Ya existe un proceso generate o finalize activo, o quedó un lock reciente. "
            "Consulta GET /diagnostics/payment-validation/locks o reintenta en unos minutos "
            "si el lock ya expiró."
        ),
        "next_action": (
            "Ejecute POST /diagnostics/payment-validation/locks/cleanup-expired "
            "(limpia expirados y locks legacy de 24h) y reintente generate/finalize. "
            "Si persiste, POST .../locks/release-stale con confirm=true."
        ),
        "locks": locks,
    }
