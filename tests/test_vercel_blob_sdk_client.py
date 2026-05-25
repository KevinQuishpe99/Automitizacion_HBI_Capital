"""Tests de VercelBlobSdkClient (SDK vercel.blob, sin URLs privadas manuales)."""

from __future__ import annotations

import asyncio
import inspect
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.adapters.secondary.vercel_blob_client import (
    VercelBlobHttpClient,
    VercelBlobSdkClient,
    create_vercel_blob_client_from_env,
)
from app.adapters.secondary.vercel_blob_job_store import VercelBlobJobStore


def test_sdk_client_source_does_not_build_private_blob_hostname() -> None:
    source = inspect.getsource(VercelBlobSdkClient)
    assert "private.blob.vercel-storage.com" not in source
    assert "_blob_url" not in source


def test_create_from_env_returns_sdk_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BLOB_READ_WRITE_TOKEN", "vercel_blob_rw_teststoreid_abc123")
    client = create_vercel_blob_client_from_env()
    assert isinstance(client, VercelBlobSdkClient)


def test_get_json_missing_returns_none() -> None:
    async def run() -> None:
        client = VercelBlobSdkClient(token="vercel_blob_rw_teststoreid_abc123")
        with patch("vercel.blob.get_async", new_callable=AsyncMock) as mock_get:
            from vercel.blob.errors import BlobNotFoundError

            mock_get.side_effect = BlobNotFoundError()
            result = await client.get_json("jobs/new/meta.json")
            assert result is None
            mock_get.assert_awaited_once()

    asyncio.run(run())


def test_put_json_and_get_json_roundtrip() -> None:
    async def run() -> None:
        client = VercelBlobSdkClient(token="vercel_blob_rw_teststoreid_abc123")
        payload = {"job_id": "j-new", "status": "queued"}

        put_result = MagicMock(pathname="jobs/j-new/meta.json", url="https://blob.example/jobs/j-new/meta.json")
        put_result.content_type = "application/json"
        get_result = MagicMock(
            status_code=200,
            content=b'{"job_id":"j-new","status":"queued"}',
        )

        with (
            patch("vercel.blob.put_async", new_callable=AsyncMock, return_value=put_result) as mock_put,
            patch("vercel.blob.get_async", new_callable=AsyncMock, return_value=get_result) as mock_get,
        ):
            await client.put_json("jobs/j-new/meta.json", payload)
            loaded = await client.get_json("jobs/j-new/meta.json")

        assert loaded == payload
        mock_put.assert_awaited_once()
        mock_get.assert_awaited_once()

    asyncio.run(run())


def test_update_job_new_without_existing_meta() -> None:
    async def run() -> None:
        store = VercelBlobJobStore.with_memory_blob()
        await store.update_job("job-new-1", {"status": "queued", "type": "amortization_dry_run"})
        job = await store.get_job("job-new-1")
        assert job is not None
        assert job["status"] == "queued"

    asyncio.run(run())


def test_ssl_error_maps_without_verify_false() -> None:
    async def run() -> None:
        client = VercelBlobSdkClient(token="vercel_blob_rw_teststoreid_abc123")
        ssl_exc = httpx.ConnectError(
            "certificate verify failed: Hostname mismatch",
            request=httpx.Request("GET", "https://example.com"),
        )
        with patch("vercel.blob.get_async", new_callable=AsyncMock, side_effect=ssl_exc):
            with pytest.raises(Exception) as exc_info:
                await client.get_bytes("jobs/x/meta.json")
        message = str(exc_info.value).lower()
        assert "verify=false" not in message
        assert "ssl" in message or "tls" in message or "hostname" in message

    asyncio.run(run())


def test_http_client_get_delegates_to_sdk_not_private_url() -> None:
    """VercelBlobHttpClient.get_bytes no debe llamar _http_get con hostname privado inventado."""

    async def run() -> None:
        http_client = VercelBlobHttpClient(
            token="vercel_blob_rw_teststoreid_abc123",
            store_id="teststoreid",
            max_retries=0,
        )
        with patch.object(
            VercelBlobSdkClient,
            "get_bytes",
            new_callable=AsyncMock,
            return_value=b"{}",
        ) as mock_sdk_get:
            result = await http_client.get_bytes("jobs/x/meta.json")
        assert result == b"{}"
        mock_sdk_get.assert_awaited_once_with("jobs/x/meta.json")

    asyncio.run(run())


def test_module_docstring_discourages_manual_private_urls() -> None:
    text = (Path(__file__).resolve().parents[1] / "app/adapters/secondary/vercel_blob_client.py").read_text(
        encoding="utf-8"
    )
    assert "private.blob.vercel-storage.com" in text
    assert "SSL hostname mismatch" in text or "hostname mismatch" in text.lower()
