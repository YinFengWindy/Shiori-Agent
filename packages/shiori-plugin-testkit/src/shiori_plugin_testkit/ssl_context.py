"""Test-session reuse of the TLS contexts httpx builds for every transport.

httpx 0.28 calls ``httpx._transports.default.create_ssl_context`` from each
``HTTPTransport`` / ``AsyncHTTPTransport`` constructor, and every call reloads the
CA bundle (~0.15s; three times per client under a system proxy). Third-party SDKs
such as python-telegram-bot build their own clients, so the host's shared context
cannot reach them. Patching that module-level name is the narrowest point that
covers every httpx client without touching production code or ``ssl`` itself.

Cached contexts are shared and mutable for the whole session: httpcore sets ALPN
on them per connection (HTTP/1.1 and HTTP/2 clients would overwrite each other),
so tests must not mutate a context they got from httpx.
"""

from __future__ import annotations

import os
import ssl
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

import httpx._transports.default as httpx_transport

SslContextFactory = Callable[..., ssl.SSLContext]

_ENV_KEYS = ("SSL_CERT_FILE", "SSL_CERT_DIR")
# httpx does not re-export this name from its transport module, hence getattr.
_FACTORY_NAME = "create_ssl_context"


def caching_ssl_context_factory(create: SslContextFactory) -> SslContextFactory:
    """Wraps httpx's factory so equal requests reuse one context per session.

    Only the default ``verify=True/False`` without ``cert`` is cached; the key also
    carries ``trust_env`` and the ``SSL_CERT_FILE`` / ``SSL_CERT_DIR`` values httpx
    would read, so tests that change those variables still get a matching context.
    Anything else (an explicit context, a CA path, a client certificate) goes
    straight to httpx unchanged.
    """
    contexts: dict[tuple[Any, ...], ssl.SSLContext] = {}

    def create_ssl_context(
        verify: ssl.SSLContext | str | bool = True,
        cert: Any = None,
        trust_env: bool = True,
    ) -> ssl.SSLContext:
        if not isinstance(verify, bool) or cert is not None:
            return create(verify=verify, cert=cert, trust_env=trust_env)
        key = (verify, trust_env, *(os.environ.get(name) for name in _ENV_KEYS))
        context = contexts.get(key)
        if context is None:
            context = create(verify=verify, cert=cert, trust_env=trust_env)
            contexts[key] = context
        return context

    return create_ssl_context


@contextmanager
def share_httpx_ssl_contexts() -> Iterator[None]:
    """Routes every httpx transport through one cache until the block exits."""
    original: SslContextFactory = getattr(httpx_transport, _FACTORY_NAME)
    setattr(httpx_transport, _FACTORY_NAME, caching_ssl_context_factory(original))
    try:
        yield
    finally:
        setattr(httpx_transport, _FACTORY_NAME, original)
