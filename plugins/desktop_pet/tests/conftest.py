"""Shared Bilibili platform double for the QR-login tests."""

import asyncio

import httpx
import pytest

LOGIN_COOKIES = {
    "SESSDATA": "sess%2C1%2Cabc",
    "bili_jct": "jct",
    "DedeUserID": "42",
    "DedeUserID__ckMd5": "md5",
}


class FakeBilibili:
    """Answers the generate/poll/nav endpoints from mutable scripted state."""

    login_cookies = LOGIN_COOKIES

    def __init__(self) -> None:
        self.scan_code = 86101
        self.login_valid = True
        self.issued = 0
        self.requests: list[httpx.Request] = []
        # While set, requests whose path ends with ``hold_path`` wait for the
        # gate to be released; ``held`` counts the parked requests.
        self.gate: asyncio.Event | None = None
        self.hold_path = "/qrcode/poll"
        self.held = 0
        self.transport = httpx.MockTransport(self._handle)

    async def wait_held(self, count: int) -> None:
        """Yield until ``count`` requests are parked at ``gate``."""
        while self.held < count:
            await asyncio.sleep(0)

    async def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if self.gate is not None and path.endswith(self.hold_path):
            self.held += 1
            await self.gate.wait()
        if path.endswith("/qrcode/generate"):
            self.issued += 1
            key = f"key-{self.issued}"
            data = {
                "url": f"https://account.bilibili.com/scan?{key}",
                "qrcode_key": key,
            }
            return httpx.Response(200, json={"code": 0, "message": "0", "data": data})
        if path.endswith("/qrcode/poll"):
            return self._poll()
        if path.endswith("/web-interface/nav"):
            session = request.headers.get("cookie", "")
            if self.login_valid and f"SESSDATA={LOGIN_COOKIES['SESSDATA']}" in session:
                data = {"isLogin": True, "mid": 42, "uname": "主播"}
                return httpx.Response(200, json={"code": 0, "data": data})
            return httpx.Response(
                200,
                json={
                    "code": -101,
                    "message": "账号未登录",
                    "data": {"isLogin": False},
                },
            )
        raise AssertionError(f"unexpected request {request.url}")

    def _poll(self) -> httpx.Response:
        success = self.scan_code == 0
        data = {
            "url": "https://passport.biligame.com/crossDomain?..." if success else "",
            "refresh_token": "refresh" if success else "",
            "timestamp": 0,
            "code": self.scan_code,
            "message": "",
        }
        headers = (
            [
                ("set-cookie", f"{name}={value}; Path=/; Domain=bilibili.com")
                for name, value in LOGIN_COOKIES.items()
            ]
            if success
            else []
        )
        return httpx.Response(
            200, headers=headers, json={"code": 0, "message": "0", "data": data}
        )


@pytest.fixture
def bilibili() -> FakeBilibili:
    """A fresh scripted Bilibili for each test; never touches the network."""
    return FakeBilibili()
