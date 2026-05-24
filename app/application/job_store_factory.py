import os
from typing import TYPE_CHECKING

from app.adapters.secondary.memory_job_store import MemoryJobStore
from app.application.job_store_settings import (
    has_blob_token,
    is_vercel_runtime,
    job_store_backend,
)
from app.domain.ports.job_store import JobStore

if TYPE_CHECKING:
    from app.adapters.secondary.vercel_blob_job_store import VercelBlobJobStore

_store: JobStore | None = None

_LOCK_GENERATE = "payment_validation:generate"
_LOCK_FINALIZE = "payment_validation:finalize"
_LOCK_HOLDER = "global"
_LOCK_TTL_SECONDS = 86_400


def _create_memory_store() -> MemoryJobStore:
    return MemoryJobStore()


def _create_vercel_blob_store() -> "VercelBlobJobStore":
    from app.adapters.secondary.vercel_blob_job_store import VercelBlobJobStore

    return VercelBlobJobStore.from_env()


def _resolve_job_store() -> JobStore:
    backend = job_store_backend()

    if backend == "memory":
        return _create_memory_store()

    if backend == "vercel_blob":
        if not has_blob_token():
            raise RuntimeError(
                "JOB_STORE_BACKEND=vercel_blob requires BLOB_READ_WRITE_TOKEN"
            )
        return _create_vercel_blob_store()

    if backend and backend not in ("", "auto"):
        raise RuntimeError(f"Unknown JOB_STORE_BACKEND: {backend!r}")

    # Auto: Vercel + token → Blob; si no, memoria (Render/local/tests)
    if is_vercel_runtime() and has_blob_token():
        return _create_vercel_blob_store()

    return _create_memory_store()


def get_job_store() -> JobStore:
    """
    Punto central de inyección del JobStore.

    - ``JOB_STORE_BACKEND=memory`` → MemoryJobStore
    - ``JOB_STORE_BACKEND=vercel_blob`` → VercelBlobJobStore (requiere token)
    - Por defecto en Vercel con ``BLOB_READ_WRITE_TOKEN`` → VercelBlobJobStore
    - En otro caso → MemoryJobStore (Render/local/tests)
    """
    global _store
    if _store is not None:
        return _store
    _store = _resolve_job_store()
    return _store


def configure_job_store(store: JobStore) -> None:
    """Tests o arranque explícito: sustituye el singleton."""
    global _store
    _store = store


def reset_job_store_singleton() -> None:
    """Tests de factory: fuerza re-resolución del backend según env."""
    global _store
    _store = None


def reset_job_store_for_tests() -> None:
    """Vacía jobs y locks del singleton actual (sin cambiar la instancia)."""
    store = get_job_store()

    from app.adapters.secondary.vercel_blob_client import InMemoryVercelBlobClient
    from app.adapters.secondary.vercel_blob_job_store import VercelBlobJobStore

    if isinstance(store, MemoryJobStore):
        store.clear_all()
    elif isinstance(store, VercelBlobJobStore) and isinstance(
        store._blob, InMemoryVercelBlobClient
    ):
        store._blob.clear()

    from app.application.job_manager import JobManager

    jm = JobManager()
    jm._generate_active = False
    jm._finalize_active = False


def payment_validation_lock_keys() -> tuple[str, str]:
    return _LOCK_GENERATE, _LOCK_FINALIZE
