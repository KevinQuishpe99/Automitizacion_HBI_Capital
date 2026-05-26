import os
from typing import TYPE_CHECKING

from app.adapters.secondary.memory_job_store import MemoryJobStore
from app.application.job_store_settings import (
    default_lock_ttl_seconds,
    has_blob_token,
    is_vercel_runtime,
    job_store_backend,
    payment_validation_locks_enabled,
)
from app.domain.ports.job_store import JobStore

if TYPE_CHECKING:
    from app.adapters.secondary.vercel_blob_job_store import VercelBlobJobStore

_store: JobStore | None = None

_LOCK_GENERATE = "payment_validation:generate"
_LOCK_FINALIZE = "payment_validation:finalize"
_LOCK_HOLDER = "global"
def lock_ttl_seconds() -> int:
    """TTL de locks generate/finalize (env LOCK_TTL_SECONDS, default 900)."""
    return default_lock_ttl_seconds()


# Alias para tests que importan el valor por defecto del entorno actual.
_LOCK_TTL_SECONDS = lock_ttl_seconds()


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

    # Auto: con token → Blob (API y worker Services comparten Blob aunque VERCEL!=1 en worker)
    if has_blob_token():
        return _create_vercel_blob_store()

    return _create_memory_store()


def resolved_job_store_backend_label() -> str:
    """Etiqueta del backend efectivo (sin secretos)."""
    explicit = job_store_backend()
    if explicit:
        return explicit
    if has_blob_token():
        return "vercel_blob_auto"
    return "memory_auto"


def safe_runtime_config() -> dict[str, str | bool]:
    """Metadata segura para diagnóstico HTTP (sin tokens)."""
    from app.application.job_runner_settings import job_runner_backend, vercel_workflows_enabled

    import os

    store = get_job_store()
    return {
        "job_store_backend": resolved_job_store_backend_label(),
        "job_runner_backend": job_runner_backend(),
        "vercel_workflows_enabled": vercel_workflows_enabled(),
        "has_blob_token": has_blob_token(),
        "has_blob_store_id": bool((os.getenv("BLOB_STORE_ID") or "").strip()),
        "store_class": type(store).__name__,
        "vercel_env_set": is_vercel_runtime(),
        "lock_ttl_seconds": lock_ttl_seconds(),
        "payment_validation_locks_enabled": payment_validation_locks_enabled(),
    }


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
