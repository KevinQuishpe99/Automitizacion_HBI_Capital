import asyncio
import time
from copy import deepcopy
from typing import Any

from app.domain.ports.job_store import JobStore


class MemoryJobStore:
    """JobStore en RAM (Render/local/dev). Compartido por JobManager y routers sharepoint."""

    def __init__(self) -> None:
        self._job_lock = asyncio.Lock()
        self._jobs: dict[str, dict[str, Any]] = {}
        self._locks: dict[str, dict[str, Any]] = {}

    async def create_job(self, job_id: str, record: dict[str, Any]) -> None:
        async with self._job_lock:
            self._jobs[job_id] = deepcopy(record)

    async def get_job(self, job_id: str) -> dict[str, Any] | None:
        async with self._job_lock:
            job = self._jobs.get(job_id)
            return deepcopy(job) if job is not None else None

    async def update_job(self, job_id: str, updates: dict[str, Any]) -> None:
        async with self._job_lock:
            current = self._jobs.get(job_id, {})
            current.update(updates)
            self._jobs[job_id] = current

    async def complete_job(self, job_id: str, result: dict[str, Any]) -> None:
        await self.update_job(
            job_id,
            {"status": "completed", "result": result, "error": None},
        )

    async def fail_job(self, job_id: str, error: dict[str, Any]) -> None:
        await self.update_job(
            job_id,
            {"status": "failed", "error": error, "result": None},
        )

    async def append_event(self, job_id: str, event: dict[str, Any]) -> None:
        async with self._job_lock:
            current = self._jobs.get(job_id, {})
            events = list(current.get("events") or [])
            events.append(deepcopy(event))
            current["events"] = events
            self._jobs[job_id] = current

    async def acquire_lock(self, key: str, holder: str, ttl_seconds: int) -> bool:
        async with self._job_lock:
            now = time.monotonic()
            existing = self._locks.get(key)
            if existing is not None:
                expires_at = existing.get("expires_at")
                if expires_at is not None and now >= expires_at:
                    pass
                elif existing.get("holder") == holder:
                    self._locks[key] = {
                        "holder": holder,
                        "expires_at": now + ttl_seconds if ttl_seconds > 0 else None,
                    }
                    return True
                else:
                    return False
            self._locks[key] = {
                "holder": holder,
                "expires_at": now + ttl_seconds if ttl_seconds > 0 else None,
            }
            return True

    async def release_lock(self, key: str, holder: str) -> None:
        async with self._job_lock:
            existing = self._locks.get(key)
            if existing is not None and existing.get("holder") == holder:
                del self._locks[key]

    async def is_lock_held(self, key: str) -> bool:
        async with self._job_lock:
            existing = self._locks.get(key)
            if existing is None:
                return False
            expires_at = existing.get("expires_at")
            if expires_at is not None and time.monotonic() >= expires_at:
                del self._locks[key]
                return False
            return True

    def clear_all(self) -> None:
        """Solo tests: vacía jobs y locks."""
        self._jobs.clear()
        self._locks.clear()
