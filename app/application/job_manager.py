from typing import Any

from app.application.job_store_factory import (
    _LOCK_FINALIZE,
    _LOCK_GENERATE,
    _LOCK_HOLDER,
    _LOCK_TTL_SECONDS,
    get_job_store,
)
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
        # Compatibilidad con tests que resetean flags directamente (Fase 2).
        self._generate_active = False
        self._finalize_active = False

    @property
    def store(self) -> JobStore:
        return get_job_store()

    async def set_job(self, job_id: str, updates: dict[str, Any]) -> None:
        await self.store.update_job(job_id, updates)

    async def get_job(self, job_id: str) -> dict[str, Any] | None:
        return await self.store.get_job(job_id)

    async def try_start_generate(self) -> bool:
        """Intenta iniciar un flujo generate. Retorna True si tiene éxito."""
        store = self.store
        if await store.is_lock_held(_LOCK_GENERATE) or await store.is_lock_held(_LOCK_FINALIZE):
            self._generate_active = False
            self._finalize_active = await store.is_lock_held(_LOCK_FINALIZE)
            return False
        acquired = await store.acquire_lock(_LOCK_GENERATE, _LOCK_HOLDER, _LOCK_TTL_SECONDS)
        self._generate_active = acquired
        return acquired

    async def finish_generate(self) -> None:
        await self.store.release_lock(_LOCK_GENERATE, _LOCK_HOLDER)
        self._generate_active = False

    async def try_start_finalize(self) -> bool:
        """Intenta iniciar un flujo finalize. Retorna True si tiene éxito."""
        store = self.store
        if await store.is_lock_held(_LOCK_GENERATE) or await store.is_lock_held(_LOCK_FINALIZE):
            self._finalize_active = False
            self._generate_active = await store.is_lock_held(_LOCK_GENERATE)
            return False
        acquired = await store.acquire_lock(_LOCK_FINALIZE, _LOCK_HOLDER, _LOCK_TTL_SECONDS)
        self._finalize_active = acquired
        return acquired

    async def finish_finalize(self) -> None:
        await self.store.release_lock(_LOCK_FINALIZE, _LOCK_HOLDER)
        self._finalize_active = False
