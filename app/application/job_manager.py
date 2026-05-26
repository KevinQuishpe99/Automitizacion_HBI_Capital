from typing import Any

from app.application.job_store_factory import (
    _LOCK_FINALIZE,
    _LOCK_GENERATE,
    _LOCK_HOLDER,
    get_job_store,
    lock_ttl_seconds,
)
from app.application.job_store_settings import payment_validation_locks_enabled
from app.domain.ports.job_store import JobStore


class JobManager:
    """Fachada singleton sobre JobStore para payment-validation (generate/finalize/amortization)."""

    _instance: "JobManager | None" = None

    def __new__(cls) -> "JobManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_state()
        return cls._instance

    def _init_state(self) -> None:
        self._generate_active = False
        self._finalize_active = False

    @property
    def store(self) -> JobStore:
        return get_job_store()

    async def set_job(self, job_id: str, updates: dict[str, Any]) -> None:
        await self.store.update_job(job_id, updates)

    async def get_job(self, job_id: str) -> dict[str, Any] | None:
        return await self.store.get_job(job_id)

    async def _release_all_payment_validation_locks(self) -> None:
        """Libera locks huérfanos en Blob (p. ej. tras generate sin finish en worker)."""
        await self.store.release_lock(_LOCK_GENERATE, _LOCK_HOLDER)
        await self.store.release_lock(_LOCK_FINALIZE, _LOCK_HOLDER)
        self._generate_active = False
        self._finalize_active = False

    async def _purge_expired_locks(self) -> None:
        store = self.store
        for key in (_LOCK_GENERATE, _LOCK_FINALIZE):
            cleanup = getattr(store, "cleanup_expired_lock", None)
            if callable(cleanup):
                await cleanup(key)
            else:
                await store.is_lock_held(key)

    async def try_start_generate(self) -> bool:
        """Intenta iniciar un flujo generate. Retorna True si tiene éxito."""
        if not payment_validation_locks_enabled():
            await self._release_all_payment_validation_locks()
            return True

        store = self.store
        await self._purge_expired_locks()
        if await store.is_lock_held(_LOCK_GENERATE) or await store.is_lock_held(_LOCK_FINALIZE):
            self._generate_active = False
            self._finalize_active = await store.is_lock_held(_LOCK_FINALIZE)
            return False
        acquired = await store.acquire_lock(_LOCK_GENERATE, _LOCK_HOLDER, lock_ttl_seconds())
        self._generate_active = acquired
        return acquired

    async def finish_generate(self) -> None:
        if not payment_validation_locks_enabled():
            await self.store.release_lock(_LOCK_GENERATE, _LOCK_HOLDER)
            self._generate_active = False
            return
        await self.store.release_lock(_LOCK_GENERATE, _LOCK_HOLDER)
        self._generate_active = False

    async def try_start_finalize(self) -> bool:
        """Intenta iniciar un flujo finalize. Retorna True si tiene éxito."""
        if not payment_validation_locks_enabled():
            await self._release_all_payment_validation_locks()
            return True

        store = self.store
        await self._purge_expired_locks()
        if await store.is_lock_held(_LOCK_GENERATE) or await store.is_lock_held(_LOCK_FINALIZE):
            self._finalize_active = False
            self._generate_active = await store.is_lock_held(_LOCK_GENERATE)
            return False
        acquired = await store.acquire_lock(_LOCK_FINALIZE, _LOCK_HOLDER, lock_ttl_seconds())
        self._finalize_active = acquired
        return acquired

    async def finish_finalize(self) -> None:
        if not payment_validation_locks_enabled():
            await self.store.release_lock(_LOCK_FINALIZE, _LOCK_HOLDER)
            self._finalize_active = False
            return
        await self.store.release_lock(_LOCK_FINALIZE, _LOCK_HOLDER)
        self._finalize_active = False
