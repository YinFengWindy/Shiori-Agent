from __future__ import annotations

import pytest

from plugins.qqbot.backend.account_dispatch import _AccountDispatchMixin
from plugins.qqbot.backend.channel import QQBotChannel


class _Dispatch(_AccountDispatchMixin):
    def __init__(self):
        self._channels = {
            "100": QQBotChannel("100", "first"),
            "200": QQBotChannel("200", "second"),
        }


def test_targets_route_only_to_the_application_they_name():
    dispatch = _Dispatch()
    assert dispatch._for_chat("c2c:200:opaque-user")._app_id == "200"
    with pytest.raises(ValueError, match="作用域"):
        dispatch._for_chat("c2c:unscoped-user")
    with pytest.raises(RuntimeError, match="未连接"):
        dispatch._for_chat("c2c:300:opaque-user")
    del dispatch._channels["200"]
    with pytest.raises(RuntimeError, match="未连接"):
        dispatch._for_chat("c2c:200:opaque-user")
