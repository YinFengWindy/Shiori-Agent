"""httpx TLS contexts are reused across transports only for equal requests."""

from __future__ import annotations

import ssl
from typing import Any

import httpx
import httpx._transports.default as httpx_transport
import pytest

from shiori_plugin_testkit.ssl_context import (
    caching_ssl_context_factory,
    share_httpx_ssl_contexts,
)


class _RecordingFactory:
    """Stands in for httpx's factory and records every context it builds."""

    def __init__(self) -> None:
        self.calls: list[tuple[Any, Any, bool]] = []

    def __call__(
        self, verify: Any = True, cert: Any = None, trust_env: bool = True
    ) -> ssl.SSLContext:
        self.calls.append((verify, cert, trust_env))
        return ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)


def test_equal_default_requests_build_one_context(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    monkeypatch.delenv("SSL_CERT_DIR", raising=False)
    create = _RecordingFactory()
    cached = caching_ssl_context_factory(create)

    first = cached(verify=True, cert=None, trust_env=True)
    assert cached(verify=True, cert=None, trust_env=True) is first
    insecure = cached(verify=False, cert=None, trust_env=True)
    no_env = cached(verify=True, cert=None, trust_env=False)

    assert len({id(first), id(insecure), id(no_env)}) == 3
    assert create.calls == [
        (True, None, True),
        (False, None, True),
        (True, None, False),
    ]


def test_certificate_environment_is_part_of_the_cache_key(
    monkeypatch: pytest.MonkeyPatch, tmp_path
):
    monkeypatch.delenv("SSL_CERT_DIR", raising=False)
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    create = _RecordingFactory()
    cached = caching_ssl_context_factory(create)
    default = cached(verify=True, cert=None, trust_env=True)

    monkeypatch.setenv("SSL_CERT_FILE", str(tmp_path / "a.pem"))
    from_file = cached(verify=True, cert=None, trust_env=True)
    monkeypatch.setenv("SSL_CERT_DIR", str(tmp_path))
    from_dir = cached(verify=True, cert=None, trust_env=True)

    assert len({id(default), id(from_file), id(from_dir)}) == 3
    assert len(create.calls) == 3


def test_explicit_contexts_and_client_certs_bypass_the_cache():
    create = _RecordingFactory()
    cached = caching_ssl_context_factory(create)
    explicit = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)

    cached(verify=explicit, cert=None, trust_env=True)
    cached(verify=explicit, cert=None, trust_env=True)
    cached(verify=True, cert="client.pem", trust_env=True)
    cached(verify=True, cert="client.pem", trust_env=True)

    assert create.calls == [
        (explicit, None, True),
        (explicit, None, True),
        (True, "client.pem", True),
        (True, "client.pem", True),
    ]


def test_share_block_patches_httpx_transports_and_restores_on_exit():
    before = getattr(httpx_transport, "create_ssl_context")
    with share_httpx_ssl_contexts():
        assert getattr(httpx_transport, "create_ssl_context") is not before
        first = httpx.AsyncHTTPTransport()
        second = httpx.AsyncHTTPTransport()
        assert first._pool._ssl_context is second._pool._ssl_context
    assert getattr(httpx_transport, "create_ssl_context") is before
