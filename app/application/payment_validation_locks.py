"""Estado y liberación de locks generate/finalize (Blob compartido Render + Vercel)."""

from __future__ import annotations

from app.application.job_store_factory import (
    _LOCK_FINALIZE,
    _LOCK_GENERATE,
    _LOCK_HOLDER,
    get_job_store,
)


async def lock_status() -> dict[str, bool | str]:
    store = get_job_store()
    gen = await store.is_lock_held(_LOCK_GENERATE)
    fin = await store.is_lock_held(_LOCK_FINALIZE)
    return {
        "generate_lock_held": gen,
        "finalize_lock_held": fin,
        "lock_holder": _LOCK_HOLDER,
        "generate_lock_key": _LOCK_GENERATE,
        "finalize_lock_key": _LOCK_FINALIZE,
    }


async def release_all_payment_validation_locks() -> dict[str, bool]:
    store = get_job_store()
    await store.release_lock(_LOCK_GENERATE, _LOCK_HOLDER)
    await store.release_lock(_LOCK_FINALIZE, _LOCK_HOLDER)
    from app.application.job_manager import JobManager

    jm = JobManager()
    jm._generate_active = False
    jm._finalize_active = False
    return await lock_status()
