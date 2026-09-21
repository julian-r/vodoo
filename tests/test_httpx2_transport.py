"""HTTPX2 transport migration regression tests."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import httpx2
import pytest

from vodoo.aio.transport import AsyncLegacyTransport
from vodoo.transport import LegacyTransport


def _transport_kwargs() -> dict[str, str]:
    return {
        "url": "https://example.invalid",
        "database": "test",
        "username": "admin",
        "password": "secret",
    }


def test_sync_transport_uses_httpx2_client() -> None:
    transport = LegacyTransport(**_transport_kwargs())
    try:
        assert isinstance(transport._http, httpx2.Client)
        assert transport._http.headers["user-agent"].startswith("python-httpx2/")
        assert transport._is_retryable("search", httpx2.ConnectError("failed"))
        assert transport._is_retryable("read", httpx2.ReadTimeout("timed out"))
        assert transport._is_retryable("fields_get", httpx2.WriteTimeout("timed out"))
        assert not transport._is_retryable("write", httpx2.ConnectError("failed"))
    finally:
        transport.close()


def test_async_transport_uses_httpx2_client() -> None:
    async def check() -> None:
        transport = AsyncLegacyTransport(**_transport_kwargs())
        try:
            assert isinstance(transport._http, httpx2.AsyncClient)
            assert transport._http.headers["user-agent"].startswith("python-httpx2/")
            assert transport._is_retryable("search_read", httpx2.ConnectError("failed"))
            assert not transport._is_retryable("create", httpx2.ConnectError("failed"))
        finally:
            await transport.close()

    asyncio.run(check())


def test_transport_preserves_environment_and_enables_http2() -> None:
    with patch("vodoo.transport.httpx.Client") as client:
        LegacyTransport(**_transport_kwargs())

    client.assert_called_once_with(timeout=30, headers={}, trust_env=True, http2=True)


def test_httpx2_uses_system_trust_store_by_default() -> None:
    context = httpx2.create_ssl_context()
    assert type(context).__module__ == "truststore._api"


def test_ssl_cert_file_environment_is_honored(monkeypatch: pytest.MonkeyPatch) -> None:
    missing_ca = "/definitely/missing-vodoo-ca.pem"
    monkeypatch.setenv("SSL_CERT_FILE", missing_ca)

    with pytest.raises(FileNotFoundError):
        LegacyTransport(**_transport_kwargs())
