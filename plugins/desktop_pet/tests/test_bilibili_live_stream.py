"""Which connection failures are retried, end the run, or are bugs."""

import httpx
import pytest
from websockets.exceptions import ConnectionClosedError

from plugins.desktop_pet.backend.bilibili_api import BilibiliApiError
from plugins.desktop_pet.backend.bilibili_danmaku import DanmakuFormatError
from plugins.desktop_pet.backend.bilibili_live_packets import LivePacketError
from plugins.desktop_pet.backend.bilibili_live_stream import (
    FailureKind,
    LiveAuthRejected,
    LiveDisconnected,
    LiveIdentityRejected,
    failure_kind,
)
from plugins.desktop_pet.backend.bilibili_login import BilibiliLoginRequired


def http_error(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://api.live.bilibili.com/x")
    response = httpx.Response(status, request=request)
    return httpx.HTTPStatusError("x", request=request, response=response)


@pytest.mark.parametrize(
    ("error", "kind"),
    [
        (LiveDisconnected("silent"), FailureKind.TRANSIENT),
        (TimeoutError(), FailureKind.TRANSIENT),
        (ConnectionClosedError(None, None), FailureKind.TRANSIENT),
        (httpx.ConnectError("down"), FailureKind.TRANSIENT),
        (http_error(502), FailureKind.TRANSIENT),
        (http_error(412), FailureKind.REJECTED),
        (BilibiliApiError("code=-352"), FailureKind.REJECTED),
        (LiveAuthRejected("code=-101"), FailureKind.REJECTED),
        (BilibiliLoginRequired("失效"), FailureKind.LOGIN),
        (LiveIdentityRejected("匿名"), FailureKind.LOGIN),
        (LivePacketError("坏包"), None),
        (DanmakuFormatError("坏弹幕"), None),
        (KeyError("bug"), None),
    ],
)
def test_failures_are_classified(error, kind):
    assert failure_kind(error) == kind
