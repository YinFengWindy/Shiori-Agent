from __future__ import annotations

import logging
from unittest.mock import AsyncMock

import pytest

from plugins.qq.backend.accounts_group_names import QQGroupNames
from plugins.qq.backend.onebot import OneBotError


@pytest.mark.asyncio
async def test_group_names_are_cached_per_account_until_they_expire():
    now = [0.0]
    fetch = AsyncMock(side_effect=["读书会", "另一个号看到的群", "新读书会"])
    names = QQGroupNames(fetch, ttl_seconds=600, clock=lambda: now[0])

    assert await names.name("account-a", "777") == "读书会"
    now[0] = 599
    assert await names.name("account-a", "777") == "读书会"
    assert await names.name("account-b", "777") == "另一个号看到的群"
    now[0] = 600
    assert await names.name("account-a", "777") == "新读书会"
    assert [call.args for call in fetch.await_args_list] == [
        ("account-a", "777"),
        ("account-b", "777"),
        ("account-a", "777"),
    ]


@pytest.mark.asyncio
async def test_failed_lookup_gives_no_name_and_is_logged(caplog):
    fetch = AsyncMock(side_effect=[OneBotError("NapCat 超时"), "读书会"])
    names = QQGroupNames(fetch)

    with caplog.at_level(logging.WARNING):
        assert await names.name("account-a", "777") is None
    assert "NapCat 超时" in caplog.text
    # A failure is not cached: the next message asks again.
    assert await names.name("account-a", "777") == "读书会"
