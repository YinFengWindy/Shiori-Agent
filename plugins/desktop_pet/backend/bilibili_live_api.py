"""Bilibili live-room HTTP reads needed before opening the danmaku stream.

Endpoints (blivedm ``clients/web.py``; bilibili-API-collect
``docs/live/message_stream.md``; each verified read-only 2026-10):

- ``GET api.live.bilibili.com/room/v1/Room/get_info?room_id=`` accepts the
  short or real id from the room URL and returns ``data.room_id`` (real id)
  and ``data.title``.
- ``GET www.bilibili.com/`` sets the ``buvid3`` browser-fingerprint cookie.
  QR login does not deliver it, yet the stream auth packet carries it, so a
  run fetches one once and keeps it for all of its connections.
- ``GET api.bilibili.com/x/web-interface/nav`` returns ``data.wbi_img`` (the
  WBI signing keys); ``GET api.live.bilibili.com/xlive/web-room/v1/index/
  getDanmuInfo?id=&type=0`` signed with WBI returns ``data.token`` and
  ``data.host_list`` (``host``, ``wss_port``) for ``wss://host:port/sub``.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx

from .bilibili_api import (
    NAV_URL,
    BilibiliApiError,
    bilibili_get,
    response_data,
    response_payload,
)
from .bilibili_wbi import sign_wbi, wbi_mixin_key

ROOM_INFO_URL = "https://api.live.bilibili.com/room/v1/Room/get_info"
DANMU_INFO_URL = "https://api.live.bilibili.com/xlive/web-room/v1/index/getDanmuInfo"
HOMEPAGE_URL = "https://www.bilibili.com/"


@dataclass(frozen=True)
class LiveRoom:
    """A resolved room: the real id the stream needs and its current title."""

    room_id: int
    title: str


@dataclass(frozen=True)
class DanmakuEndpoint:
    """Where and with which token one stream connection authenticates."""

    urls: tuple[str, ...]
    token: str


class BilibiliLiveApi:
    """Stateless HTTP client; ``transport`` and ``now`` are injectable for tests."""

    def __init__(
        self,
        transport: httpx.AsyncBaseTransport | None = None,
        now: Callable[[], float] = time.time,
    ) -> None:
        self._transport = transport
        self._now = now

    async def fetch_room(self, room_id: int) -> LiveRoom:
        """Resolve a room id from the room URL; an unknown room is an error."""
        data = response_data(
            await bilibili_get(
                self._transport, ROOM_INFO_URL, params={"room_id": str(room_id)}
            )
        )
        real_id, title = data.get("room_id"), data.get("title")
        if not isinstance(real_id, int) or real_id <= 0 or not isinstance(title, str):
            raise BilibiliApiError("B 站直播间信息缺少 room_id 或 title")
        return LiveRoom(room_id=real_id, title=title.strip() or f"直播间 {real_id}")

    async def fetch_buvid(self) -> str:
        """Obtain a ``buvid3`` fingerprint cookie from the web homepage."""
        response = await bilibili_get(self._transport, HOMEPAGE_URL)
        buvid = response.cookies.get("buvid3")
        if not buvid:
            raise BilibiliApiError("B 站首页未下发 buvid3")
        return buvid

    async def fetch_endpoint(
        self, room_id: int, cookies: dict[str, str]
    ) -> DanmakuEndpoint:
        """Fetch a fresh stream token and hosts for a (re)connection."""
        # nav carries the WBI keys whether or not the cookies are logged in;
        # login validity is checked separately before every connection.
        nav = response_payload(
            await bilibili_get(self._transport, NAV_URL, cookies=cookies)
        )
        wbi = _dict(_dict(nav.get("data")).get("wbi_img"))
        img_url, sub_url = wbi.get("img_url"), wbi.get("sub_url")
        if not isinstance(img_url, str) or not isinstance(sub_url, str):
            raise BilibiliApiError("B 站 nav 响应缺少 wbi_img")
        params = sign_wbi(
            {"id": room_id, "type": 0},
            wbi_mixin_key(img_url, sub_url),
            int(self._now()),
        )
        data = response_data(
            await bilibili_get(
                self._transport, DANMU_INFO_URL, params=params, cookies=cookies
            )
        )
        token, hosts = data.get("token"), data.get("host_list")
        if not isinstance(token, str) or not token or not isinstance(hosts, list):
            raise BilibiliApiError("B 站弹幕服务器信息缺少 token 或 host_list")
        urls = tuple(_wss_url(host) for host in hosts)
        if not urls:
            raise BilibiliApiError("B 站弹幕服务器列表为空")
        return DanmakuEndpoint(urls=urls, token=token)


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _wss_url(host: object) -> str:
    entry = _dict(host)
    name, port = entry.get("host"), entry.get("wss_port")
    if not isinstance(name, str) or not name or not isinstance(port, int):
        raise BilibiliApiError("B 站弹幕服务器条目无效")
    return f"wss://{name}:{port}/sub"
