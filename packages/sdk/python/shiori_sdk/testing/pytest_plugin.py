"""Pytest entry point, activated when pytest and the SDK testing extra are installed."""

from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
import pytest_asyncio

from .context import FakePluginContext
from .ssl_context import share_httpx_ssl_contexts


@pytest.fixture(scope="session", autouse=True)
def shared_httpx_ssl_contexts() -> Iterator[None]:
    """Reuses test-session TLS contexts without importing host state."""
    with share_httpx_ssl_contexts():
        yield


@pytest_asyncio.fixture
async def sdk_context(tmp_path: Path) -> AsyncIterator[FakePluginContext]:
    """Provides an isolated context and always runs its registered cleanup."""
    context = FakePluginContext(plugin_dir=tmp_path)
    try:
        yield context
    finally:
        await context.aclose()
