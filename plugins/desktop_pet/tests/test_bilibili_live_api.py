"""Live-room HTTP reads against the scripted Bilibili endpoints."""

import pytest

from plugins.desktop_pet.backend.bilibili_api import BilibiliApiError
from plugins.desktop_pet.backend.bilibili_live_api import (
    BilibiliLiveApi,
    DanmakuEndpoint,
    LiveRoom,
)


async def test_room_id_from_the_url_resolves_to_real_id_and_title(bilibili):
    api = BilibiliLiveApi(bilibili.transport)
    assert await api.fetch_room(6) == LiveRoom(room_id=1001, title="测试直播间")
    with pytest.raises(BilibiliApiError, match="房间不存在"):
        await api.fetch_room(7)


async def test_buvid_comes_from_the_homepage_cookie(bilibili):
    assert await BilibiliLiveApi(bilibili.transport).fetch_buvid() == "BUVID-FAKE"


async def test_endpoint_request_is_wbi_signed_and_sends_login_cookies(bilibili):
    api = BilibiliLiveApi(bilibili.transport, now=lambda: 1702204169)
    cookies = {**bilibili.login_cookies, "buvid3": "BUVID-FAKE"}
    endpoint = await api.fetch_endpoint(1001, cookies)

    assert endpoint == DanmakuEndpoint(
        urls=("wss://comet.example:443/sub",), token="stream-token"
    )
    request = bilibili.requests[-1]
    params = dict(request.url.params)
    assert params["id"] == "1001" and params["type"] == "0"
    assert params["wts"] == "1702204169" and len(params["w_rid"]) == 32
    assert "SESSDATA=" in request.headers["cookie"]
    assert "buvid3=BUVID-FAKE" in request.headers["cookie"]
