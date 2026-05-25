"""Tests de reintentos en VercelBlobHttpClient."""

import asyncio
from unittest.mock import AsyncMock

import httpx
import pytest

from app.adapters.secondary.vercel_blob_client import (
    VercelBlobHttpError,
    VercelBlobHttpClient,
)


def _client(**kwargs: object) -> VercelBlobHttpClient:
    defaults: dict = {
        "token": "vercel_blob_rw_teststoreid_abc123",
        "store_id": "teststoreid",
        "max_retries": 3,
        "retry_base_seconds": 0.01,
        "retry_max_seconds": 0.05,
        "sleep_fn": AsyncMock(),
    }
    defaults.update(kwargs)
    return VercelBlobHttpClient(**defaults)


def _request(method: str, url: str) -> httpx.Request:
    return httpx.Request(method, url)


def test_put_retries_503_then_succeeds() -> None:
    async def run() -> None:
        client = _client()
        calls = {"n": 0}

        async def fake_put(url: str, *, headers: dict, content: bytes) -> httpx.Response:
            calls["n"] += 1
            req = _request("PUT", url)
            if calls["n"] == 1:
                resp = httpx.Response(503, request=req, text="service unavailable")
                resp.raise_for_status()
            return httpx.Response(200, request=req, json={"pathname": "jobs/x/meta.json"})

        client._http_put = fake_put  # type: ignore[method-assign]

        result = await client.put_bytes("jobs/x/meta.json", b"{}")
        assert result["pathname"] == "jobs/x/meta.json"
        assert calls["n"] == 2
        assert client._sleep.await_count == 1

    asyncio.run(run())


def test_put_401_does_not_retry() -> None:
    async def run() -> None:
        client = _client(max_retries=3)
        calls = {"n": 0}

        async def fake_put(url: str, *, headers: dict, content: bytes) -> httpx.Response:
            calls["n"] += 1
            req = _request("PUT", url)
            resp = httpx.Response(401, request=req, text="forbidden")
            resp.raise_for_status()
            return resp

        client._http_put = fake_put  # type: ignore[method-assign]

        with pytest.raises(VercelBlobHttpError) as exc_info:
            await client.put_bytes("jobs/x/meta.json", b"{}")

        err = exc_info.value
        assert err.status_code == 401
        assert err.attempt == 1
        assert calls["n"] == 1
        client._sleep.assert_not_awaited()

    asyncio.run(run())


def test_put_exhausted_retries_raises_clear_error() -> None:
    async def run() -> None:
        client = _client(max_retries=2)
        calls = {"n": 0}

        async def fake_put(url: str, *, headers: dict, content: bytes) -> httpx.Response:
            calls["n"] += 1
            req = _request("PUT", url)
            resp = httpx.Response(503, request=req, text="still down")
            resp.raise_for_status()
            return resp

        client._http_put = fake_put  # type: ignore[method-assign]

        with pytest.raises(VercelBlobHttpError) as exc_info:
            await client.put_bytes("jobs/y/meta.json", b"{}")

        err = exc_info.value
        assert err.operation == "put"
        assert err.target == "jobs/y/meta.json"
        assert err.status_code == 503
        assert err.attempt == 3
        assert "still down" in (err.response_snippet or "")
        assert calls["n"] == 3
        assert client._sleep.await_count == 2

    asyncio.run(run())
