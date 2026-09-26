"""An empty successful getUpdates batch confirms polling recovery."""

from unittest.mock import AsyncMock, Mock

import pytest
from telegram.ext import ExtBot

from plugins.telegram.backend.channel.polling import ObservedBot


@pytest.mark.asyncio
async def test_empty_successful_poll_reports_recovery(monkeypatch):
    get_updates = AsyncMock(return_value=())
    monkeypatch.setattr(ExtBot, "get_updates", get_updates)
    recovered = Mock()
    bot = ObservedBot("123:abc", recovered)
    assert await bot.get_updates(offset=10) == ()
    get_updates.assert_awaited_once_with(offset=10)
    recovered.assert_called_once()


@pytest.mark.asyncio
async def test_failed_poll_does_not_report_recovery(monkeypatch):
    get_updates = AsyncMock(side_effect=RuntimeError("network"))
    monkeypatch.setattr(ExtBot, "get_updates", get_updates)
    recovered = Mock()
    bot = ObservedBot("123:abc", recovered)
    with pytest.raises(RuntimeError):
        await bot.get_updates()
    recovered.assert_not_called()
