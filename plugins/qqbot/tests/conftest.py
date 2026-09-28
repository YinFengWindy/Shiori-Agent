"""Keeps QQBot account tests off the network when applications connect."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest


@pytest.fixture(autouse=True)
def avatar_fetch(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """Connected applications fetch no avatar unless a test sets one."""
    fetch = AsyncMock(return_value=None)
    monkeypatch.setattr("plugins.qqbot.backend.account_channel.fetch_bot_avatar", fetch)
    return fetch
