"""Bilibili web QR-login and account protocol; no storage or role policy here.

Protocol (verified 2026-10 against the live endpoints and the archived
bilibili-API-collect ``docs/login/login_action/QR.md``):

- ``GET passport.bilibili.com/x/passport-login/web/qrcode/generate`` returns
  ``data.url`` (content to encode in the QR) and ``data.qrcode_key`` (valid 180 s).
- ``GET .../qrcode/poll?qrcode_key=`` always answers outer ``code`` 0; the scan
  state is ``data.code``: 86101 not scanned, 86090 scanned awaiting confirmation,
  86038 expired, 0 confirmed. On 0 the response sets the ``SESSDATA``,
  ``bili_jct``, ``DedeUserID`` and ``DedeUserID__ckMd5`` cookies and carries
  ``data.refresh_token``.
- ``GET api.bilibili.com/x/web-interface/nav`` with those cookies answers
  ``code`` 0 and ``data.isLogin`` true with ``mid``/``uname`` while the login
  is valid, and ``code`` -101 once it is not.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import httpx

QRCODE_GENERATE_URL = (
    "https://passport.bilibili.com/x/passport-login/web/qrcode/generate"
)
QRCODE_POLL_URL = "https://passport.bilibili.com/x/passport-login/web/qrcode/poll"
NAV_URL = "https://api.bilibili.com/x/web-interface/nav"
# Cookies a confirmed login must deliver; the live engine needs all of them.
REQUIRED_LOGIN_COOKIES = ("SESSDATA", "bili_jct", "DedeUserID")
_NOT_LOGGED_IN_CODE = -101
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.bilibili.com/",
}
_TIMEOUT_S = 10.0


class BilibiliApiError(RuntimeError):
    """Bilibili answered with a business code this client does not accept."""


class QrScanState(StrEnum):
    """Scan progress of one QR code, mapped from the poll ``data.code``."""

    WAITING_SCAN = "waiting_scan"
    WAITING_CONFIRM = "waiting_confirm"
    SUCCESS = "success"
    EXPIRED = "expired"


_SCAN_STATES = {
    86101: QrScanState.WAITING_SCAN,
    86090: QrScanState.WAITING_CONFIRM,
    86038: QrScanState.EXPIRED,
    0: QrScanState.SUCCESS,
}


@dataclass(frozen=True)
class QrCodeTicket:
    """A freshly issued login QR: ``url`` is encoded, ``key`` is polled."""

    url: str
    key: str


@dataclass(frozen=True)
class QrPollResult:
    """One poll answer; ``cookies``/``refresh_token`` are set only on success."""

    state: QrScanState
    cookies: dict[str, str]
    refresh_token: str


@dataclass(frozen=True)
class BilibiliAccount:
    """The account behind a valid login, as reported by the nav API."""

    uid: int
    uname: str


class BilibiliLoginApi:
    """Stateless HTTP client; ``transport`` is injectable for test doubles."""

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    async def generate_qrcode(self) -> QrCodeTicket:
        """Request a new login QR code."""
        data = _data(await self._get(QRCODE_GENERATE_URL))
        url, key = data.get("url"), data.get("qrcode_key")
        if not isinstance(url, str) or not url or not isinstance(key, str) or not key:
            raise BilibiliApiError("B 站二维码响应缺少 url 或 qrcode_key")
        return QrCodeTicket(url=url, key=key)

    async def poll_qrcode(self, key: str) -> QrPollResult:
        """Read the scan state; a confirmed scan must carry the login cookies."""
        response = await self._get(QRCODE_POLL_URL, params={"qrcode_key": key})
        data = _data(response)
        code = data.get("code")
        state = _SCAN_STATES.get(code) if isinstance(code, int) else None
        if state is None:
            raise BilibiliApiError(f"B 站扫码状态未知: {code} {data.get('message')}")
        if state is not QrScanState.SUCCESS:
            return QrPollResult(state=state, cookies={}, refresh_token="")
        cookies = {cookie.name: cookie.value or "" for cookie in response.cookies.jar}
        missing = [name for name in REQUIRED_LOGIN_COOKIES if not cookies.get(name)]
        if missing:
            raise BilibiliApiError(f"B 站登录成功但缺少 Cookie: {', '.join(missing)}")
        refresh_token = data.get("refresh_token")
        return QrPollResult(
            state=state,
            cookies=cookies,
            refresh_token=refresh_token if isinstance(refresh_token, str) else "",
        )

    async def fetch_account(self, cookies: dict[str, str]) -> BilibiliAccount | None:
        """Return the logged-in account, or ``None`` when the login is invalid."""
        response = await self._get(NAV_URL, cookies=cookies)
        if _payload(response).get("code") == _NOT_LOGGED_IN_CODE:
            return None
        data = _data(response)
        if data.get("isLogin") is not True:
            return None
        uid, uname = data.get("mid"), data.get("uname")
        if not isinstance(uid, int) or not isinstance(uname, str):
            raise BilibiliApiError("B 站账号信息缺少 mid 或 uname")
        return BilibiliAccount(uid=uid, uname=uname)

    async def _get(
        self,
        url: str,
        *,
        params: dict[str, str] | None = None,
        cookies: dict[str, str] | None = None,
    ) -> httpx.Response:
        # One short-lived client per call: login requests are rare and this
        # leaves no connection pool for the plugin lifecycle to close.
        async with httpx.AsyncClient(
            transport=self._transport,
            headers=_HEADERS,
            cookies=cookies,
            timeout=_TIMEOUT_S,
        ) as client:
            response = await client.get(url, params=params)
        response.raise_for_status()
        return response


def _payload(response: httpx.Response) -> dict[str, Any]:
    payload = response.json()
    if not isinstance(payload, dict):
        raise BilibiliApiError("B 站响应不是 JSON 对象")
    return payload


def _data(response: httpx.Response) -> dict[str, Any]:
    """Unwrap ``data`` from a response whose outer ``code`` must be 0."""
    payload = _payload(response)
    if payload.get("code") != 0:
        raise BilibiliApiError(
            f"B 站接口失败 code={payload.get('code')} msg={payload.get('message')}"
        )
    return _data_of(payload)


def _data_of(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data")
    if not isinstance(data, dict):
        raise BilibiliApiError("B 站响应缺少 data")
    return data
