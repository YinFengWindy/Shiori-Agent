from __future__ import annotations

import pytest

from plugins.qqbot.backend.account_dispatch import _AccountDispatchMixin
from plugins.qqbot.backend.channel import QQBotChannel


class _Dispatch(_AccountDispatchMixin):
    def __init__(self):
        self._channels = {
            "100": QQBotChannel("100", "legacy", scoped=False),
            "200": QQBotChannel("200", "new", scoped=True),
        }


def test_scoped_targets_never_route_to_the_legacy_application():
    dispatch = _Dispatch()
    assert dispatch._for_chat("c2c:legacy-user")._app_id == "100"
    assert dispatch._for_chat("c2c:200:opaque-user")._app_id == "200"
    with pytest.raises(RuntimeError, match="未连接"):
        dispatch._for_chat("c2c:300:opaque-user")
    del dispatch._channels["200"]
    with pytest.raises(RuntimeError, match="未连接"):
        dispatch._for_chat("c2c:200:opaque-user")
