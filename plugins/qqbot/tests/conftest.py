"""Keeps QQBot account tests off the network when applications connect."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from shiori_sdk.testing.channel_context import FakeChannelPluginContext

PLUGIN_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def avatar_fetch(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """Connected applications fetch no avatar unless a test sets one."""
    fetch = AsyncMock(return_value=None)
    monkeypatch.setattr("plugins.qqbot.backend.account_channel.fetch_bot_avatar", fetch)
    return fetch


@pytest.fixture
def setup_context() -> Callable[..., FakeChannelPluginContext]:
    """Build this plugin's SDK setup context with selected host account IDs."""

    def build(
        account_ids: Callable[[str], str] = lambda value: value,
    ) -> FakeChannelPluginContext:
        return FakeChannelPluginContext("qqbot", PLUGIN_DIR, account_ids=account_ids)

    return build
