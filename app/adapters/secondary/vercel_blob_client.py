"""
Cliente Vercel Blob para JobStore.

Producción (Vercel): ``VercelBlobSdkClient`` vía ``vercel.blob`` (get/put/delete oficiales).
Legacy HTTP: ``VercelBlobHttpClient`` solo para tests de reintentos PUT; no construye URLs
``*.private.blob.vercel-storage.com`` para lectura (provoca SSL hostname mismatch).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
from collections.abc import Awaitable, Callable
from typing import Any, Literal, Protocol, TypeVar
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

BlobReadMethod = Literal["sdk", "official_http"]

BLOB_API_VERSION = "12"
DEFAULT_API_BASE = "https://vercel.com/api/blob"

TRANSIENT_HTTP_STATUS_CODES = frozenset({408, 409, 425, 429, 500, 502, 503, 504})
NON_RETRYABLE_HTTP_STATUS_CODES = frozenset({400, 401, 403})

T = TypeVar("T")
SleepFn = Callable[[float], Awaitable[None]]


class VercelBlobHttpError(RuntimeError):
    """Error tras agotar reintentos contra Vercel Blob."""

    def __init__(
        self,
        *,
        operation: str,
        target: str,
        attempt: int,
        status_code: int | None = None,
        response_snippet: str | None = None,
        cause: BaseException | None = None,
    ) -> None:
        self.operation = operation
        self.target = target
        self.attempt = attempt
        self.status_code = status_code
        self.response_snippet = response_snippet
        parts = [
            f"Vercel Blob {operation} failed after {attempt} attempt(s)",
            f"target={target!r}",
        ]
        if status_code is not None:
            parts.append(f"status_code={status_code}")
        if response_snippet:
            parts.append(f"response={response_snippet!r}")
        super().__init__(", ".join(parts))
        self.__cause__ = cause


class VercelBlobClientProtocol(Protocol):
    async def put_bytes(
        self,
        pathname: str,
        data: bytes,
        *,
        content_type: str = "application/octet-stream",
        allow_overwrite: bool = True,
    ) -> dict[str, Any]: ...

    async def get_bytes(self, pathname: str) -> bytes | None: ...

    async def delete(self, pathname: str) -> None: ...

    async def put_json(self, pathname: str, payload: Any, *, allow_overwrite: bool = True) -> dict[str, Any]:
        ...

    async def get_json(self, pathname: str) -> Any | None:
        ...


def _read_int_env(name: str, default: int, *, minimum: int = 0) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return max(minimum, int(raw))
    except ValueError:
        return default


def _read_float_env(name: str, default: float, *, minimum: float = 0.0) -> float:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return max(minimum, float(raw))
    except ValueError:
        return default


def blob_http_max_retries() -> int:
    return _read_int_env("BLOB_HTTP_MAX_RETRIES", 3, minimum=0)


def blob_http_retry_base_seconds() -> float:
    return _read_float_env("BLOB_HTTP_RETRY_BASE_SECONDS", 0.5, minimum=0.0)


def blob_http_retry_max_seconds() -> float:
    return _read_float_env("BLOB_HTTP_RETRY_MAX_SECONDS", 4.0, minimum=0.0)


def parse_store_id_from_token(token: str) -> str:
    parts = token.split("_")
    if len(parts) < 4 or not parts[3]:
        raise ValueError("Invalid BLOB_READ_WRITE_TOKEN: cannot parse store id")
    store_id = parts[3]
    return store_id.removeprefix("store_") if store_id.startswith("store_") else store_id


def _response_snippet(response: httpx.Response | None) -> str | None:
    if response is None:
        return None
    text = (response.text or "").strip()
    if not text:
        return None
    return text[:200]


def _is_transient_http_status(status_code: int) -> bool:
    return status_code in TRANSIENT_HTTP_STATUS_CODES


def _is_non_retryable_http_status(status_code: int) -> bool:
    return status_code in NON_RETRYABLE_HTTP_STATUS_CODES


def _is_retryable_exception(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TimeoutException):
        return True
    if isinstance(exc, httpx.TransportError):
        return True
    return False


def _ssl_or_connect_hint(exc: BaseException) -> str | None:
    message = str(exc).lower()
    if "certificate" in message or "ssl" in message or "hostname" in message:
        return (
            "fallo de verificación TLS al contactar Blob; use el SDK vercel.blob "
            "(no construir URLs *.private.blob.vercel-storage.com manualmente)"
        )
    return None


def create_vercel_blob_client_from_env() -> VercelBlobClientProtocol:
    """Factory: SDK oficial en runtime; InMemory en tests vía inyección explícita."""
    return VercelBlobSdkClient.from_env()


class VercelBlobSdkClient:
    """
    Adapter sobre ``vercel.blob`` (get_async/put_async/delete_async).

    Resuelve pathname → URL vía control plane/head y ``downloadUrl``; no arma hostnames
    privados a mano desde ``BLOB_STORE_ID``.
    """

    READ_METHOD: BlobReadMethod = "sdk"

    def __init__(
        self,
        *,
        token: str,
        access: str = "private",
        timeout_seconds: float = 60.0,
    ) -> None:
        self._token = token.strip()
        self._access = "private" if access == "private" else "public"
        self._timeout = timeout_seconds
        logger.info(
            "Vercel Blob client: backend=sdk access=%s read_method=%s",
            self._access,
            self.READ_METHOD,
        )

    @classmethod
    def from_env(cls) -> VercelBlobSdkClient:
        token = (os.getenv("BLOB_READ_WRITE_TOKEN") or "").strip()
        if not token:
            raise ValueError("BLOB_READ_WRITE_TOKEN is required for VercelBlobSdkClient")
        return cls(token=token)

    def _log_operation(self, operation: str, pathname: str) -> None:
        logger.debug(
            "Vercel Blob %s pathname=%s method=%s",
            operation,
            pathname,
            self.READ_METHOD,
        )

    def _map_sdk_error(
        self,
        *,
        operation: str,
        pathname: str,
        exc: BaseException,
    ) -> VercelBlobHttpError:
        from vercel.blob.errors import BlobNotFoundError

        if isinstance(exc, BlobNotFoundError):
            return VercelBlobHttpError(
                operation=operation,
                target=pathname,
                attempt=1,
                status_code=404,
                cause=exc,
            )
        hint = _ssl_or_connect_hint(exc)
        snippet = hint or type(exc).__name__
        status_code = getattr(getattr(exc, "response", None), "status_code", None)
        logger.warning(
            "Vercel Blob %s failed pathname=%s method=%s status_code=%s error=%s",
            operation,
            pathname,
            self.READ_METHOD,
            status_code,
            type(exc).__name__,
        )
        return VercelBlobHttpError(
            operation=operation,
            target=pathname,
            attempt=1,
            status_code=status_code,
            response_snippet=snippet,
            cause=exc,
        )

    async def put_bytes(
        self,
        pathname: str,
        data: bytes,
        *,
        content_type: str = "application/octet-stream",
        allow_overwrite: bool = True,
    ) -> dict[str, Any]:
        from vercel.blob import put_async

        self._log_operation("put", pathname)
        try:
            result = await put_async(
                pathname,
                data,
                access=self._access,  # type: ignore[arg-type]
                content_type=content_type,
                add_random_suffix=False,
                overwrite=allow_overwrite,
                token=self._token,
            )
            return {
                "pathname": result.pathname,
                "url": result.url,
                "contentType": result.content_type,
            }
        except Exception as exc:
            raise self._map_sdk_error(operation="put", pathname=pathname, exc=exc) from exc

    async def get_bytes(self, pathname: str) -> bytes | None:
        from vercel.blob import get_async
        from vercel.blob.errors import BlobNotFoundError

        self._log_operation("get", pathname)
        try:
            result = await get_async(
                pathname,
                access=self._access,  # type: ignore[arg-type]
                token=self._token,
                timeout=self._timeout,
            )
            if result.status_code == 404:
                return None
            return result.content or b""
        except BlobNotFoundError:
            return None
        except Exception as exc:
            raise self._map_sdk_error(operation="get", pathname=pathname, exc=exc) from exc

    async def delete(self, pathname: str) -> None:
        from vercel.blob import delete_async

        self._log_operation("delete", pathname)
        try:
            await delete_async(pathname, token=self._token)
        except Exception as exc:
            raise self._map_sdk_error(operation="delete", pathname=pathname, exc=exc) from exc

    async def put_json(
        self,
        pathname: str,
        payload: Any,
        *,
        allow_overwrite: bool = True,
    ) -> dict[str, Any]:
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        return await self.put_bytes(
            pathname,
            data,
            content_type="application/json",
            allow_overwrite=allow_overwrite,
        )

    async def get_json(self, pathname: str) -> Any | None:
        raw = await self.get_bytes(pathname)
        if raw is None:
            return None
        return json.loads(raw.decode("utf-8"))


def _backoff_seconds(attempt_index: int, *, base: float, cap: float) -> float:
    """attempt_index: 0 = primer reintento tras fallo inicial."""
    delay = min(cap, base * (2**attempt_index))
    jitter = random.uniform(0, delay * 0.1)
    return delay + jitter


class VercelBlobHttpClient:
    """Implementación real contra Vercel Blob (httpx)."""

    def __init__(
        self,
        *,
        token: str,
        store_id: str | None = None,
        access: str = "private",
        api_base: str | None = None,
        timeout_seconds: float = 60.0,
        max_retries: int | None = None,
        retry_base_seconds: float | None = None,
        retry_max_seconds: float | None = None,
        sleep_fn: SleepFn | None = None,
    ) -> None:
        self._token = token.strip()
        self._store_id = store_id or parse_store_id_from_token(self._token)
        self._access = access
        self._api_base = (api_base or os.getenv("VERCEL_BLOB_API_URL") or DEFAULT_API_BASE).rstrip("/")
        self._timeout = timeout_seconds
        self._max_retries = max_retries if max_retries is not None else blob_http_max_retries()
        self._retry_base_seconds = (
            retry_base_seconds if retry_base_seconds is not None else blob_http_retry_base_seconds()
        )
        self._retry_max_seconds = (
            retry_max_seconds if retry_max_seconds is not None else blob_http_retry_max_seconds()
        )
        self._sleep: SleepFn = sleep_fn or asyncio.sleep

    @classmethod
    def from_env(cls) -> VercelBlobClientProtocol:
        """Runtime: SDK oficial. Tests de reintentos HTTP instancian ``VercelBlobHttpClient`` directo."""
        return create_vercel_blob_client_from_env()

    def _blob_url(self, pathname: str) -> str:
        """Solo delete legacy HTTP; no usar para GET (SSL hostname mismatch en Services)."""
        return f"https://{self._store_id}.{self._access}.blob.vercel-storage.com/{pathname}"

    def _api_headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {
            "authorization": f"Bearer {self._token}",
            "x-vercel-blob-store-id": self._store_id,
            "x-api-version": BLOB_API_VERSION,
        }
        if extra:
            headers.update(extra)
        return headers

    async def _execute_with_retry(
        self,
        operation: str,
        target: str,
        action: Callable[[], Awaitable[T]],
    ) -> T:
        max_attempts = self._max_retries + 1
        last_status: int | None = None
        last_response: httpx.Response | None = None
        last_exc: BaseException | None = None

        for attempt in range(1, max_attempts + 1):
            try:
                return await action()
            except httpx.HTTPStatusError as exc:
                response = exc.response
                last_status = response.status_code
                last_response = response
                last_exc = exc
                if _is_non_retryable_http_status(response.status_code):
                    raise VercelBlobHttpError(
                        operation=operation,
                        target=target,
                        attempt=attempt,
                        status_code=response.status_code,
                        response_snippet=_response_snippet(response),
                        cause=exc,
                    ) from exc
                if not _is_transient_http_status(response.status_code):
                    raise VercelBlobHttpError(
                        operation=operation,
                        target=target,
                        attempt=attempt,
                        status_code=response.status_code,
                        response_snippet=_response_snippet(response),
                        cause=exc,
                    ) from exc
            except Exception as exc:
                if not _is_retryable_exception(exc):
                    if isinstance(exc, VercelBlobHttpError):
                        raise
                    raise VercelBlobHttpError(
                        operation=operation,
                        target=target,
                        attempt=attempt,
                        status_code=last_status,
                        response_snippet=_response_snippet(last_response),
                        cause=exc,
                    ) from exc
                last_exc = exc

            if attempt >= max_attempts:
                break
            await self._sleep(
                _backoff_seconds(
                    attempt - 1,
                    base=self._retry_base_seconds,
                    cap=self._retry_max_seconds,
                )
            )

        raise VercelBlobHttpError(
            operation=operation,
            target=target,
            attempt=max_attempts,
            status_code=last_status,
            response_snippet=_response_snippet(last_response),
            cause=last_exc,
        )

    async def _http_put(self, url: str, *, headers: dict[str, str], content: bytes) -> httpx.Response:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.put(url, content=content, headers=headers)
            if response.status_code >= 400:
                response.raise_for_status()
            return response

    async def _http_get(self, url: str, *, headers: dict[str, str]) -> httpx.Response:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            return await client.get(url, headers=headers)

    async def _http_post(self, url: str, *, headers: dict[str, str], json_body: dict[str, Any]) -> httpx.Response:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(url, headers=headers, json=json_body)
            if response.status_code >= 400 and response.status_code != 404:
                response.raise_for_status()
            return response

    async def put_bytes(
        self,
        pathname: str,
        data: bytes,
        *,
        content_type: str = "application/octet-stream",
        allow_overwrite: bool = True,
    ) -> dict[str, Any]:
        params = f"pathname={quote(pathname, safe='')}"
        url = f"{self._api_base}/?{params}"
        headers = self._api_headers(
            {
                "x-vercel-blob-access": self._access,
                "x-content-type": content_type,
                "x-add-random-suffix": "0",
                "x-allow-overwrite": "1" if allow_overwrite else "0",
                "x-content-length": str(len(data)),
            }
        )

        async def _do_put() -> dict[str, Any]:
            response = await self._http_put(url, headers=headers, content=data)
            return response.json()

        return await self._execute_with_retry("put", pathname, _do_put)

    async def get_bytes(self, pathname: str) -> bytes | None:
        sdk = VercelBlobSdkClient(token=self._token, access=self._access, timeout_seconds=self._timeout)
        return await sdk.get_bytes(pathname)

    async def delete(self, pathname: str) -> None:
        sdk = VercelBlobSdkClient(token=self._token, access=self._access, timeout_seconds=self._timeout)
        await sdk.delete(pathname)

    async def put_json(
        self,
        pathname: str,
        payload: Any,
        *,
        allow_overwrite: bool = True,
    ) -> dict[str, Any]:
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        return await self.put_bytes(
            pathname,
            data,
            content_type="application/json",
            allow_overwrite=allow_overwrite,
        )

    async def get_json(self, pathname: str) -> Any | None:
        raw = await self.get_bytes(pathname)
        if raw is None:
            return None
        return json.loads(raw.decode("utf-8"))


class InMemoryVercelBlobClient:
    """Fake Blob para tests unitarios (sin red)."""

    def __init__(self) -> None:
        self._objects: dict[str, bytes] = {}

    def clear(self) -> None:
        self._objects.clear()

    async def put_bytes(
        self,
        pathname: str,
        data: bytes,
        *,
        content_type: str = "application/octet-stream",
        allow_overwrite: bool = True,
    ) -> dict[str, Any]:
        if pathname in self._objects and not allow_overwrite:
            raise RuntimeError(f"Blob exists: {pathname}")
        self._objects[pathname] = data
        return {"pathname": pathname, "url": f"https://fake.blob/{pathname}"}

    async def get_bytes(self, pathname: str) -> bytes | None:
        return self._objects.get(pathname)

    async def delete(self, pathname: str) -> None:
        self._objects.pop(pathname, None)

    async def put_json(
        self,
        pathname: str,
        payload: Any,
        *,
        allow_overwrite: bool = True,
    ) -> dict[str, Any]:
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        return await self.put_bytes(pathname, data, content_type="application/json", allow_overwrite=allow_overwrite)

    async def get_json(self, pathname: str) -> Any | None:
        raw = await self.get_bytes(pathname)
        if raw is None:
            return None
        return json.loads(raw.decode("utf-8"))
