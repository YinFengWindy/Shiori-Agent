"""The Bilibili QR/nav protocol is mapped exactly, with no silent defaults."""

import httpx
import pytest

from plugins.desktop_pet.backend.bilibili_api import (
    BilibiliApiError,
    BilibiliLoginApi,
    QrScanState,
)


@pytest.mark.parametrize(
    ("code", "state"),
    [
        (86101, QrScanState.WAITING_SCAN),
        (86090, QrScanState.WAITING_CONFIRM),
        (86038, QrScanState.EXPIRED),
    ],
)
async def test_pending_scan_states_carry_no_credentials(bilibili, code, state):
    api = BilibiliLoginApi(bilibili.transport)
    ticket = await api.generate_qrcode()
    bilibili.scan_code = code
    result = await api.poll_qrcode(ticket.key)
    assert (result.state, result.cookies, result.refresh_token) == (state, {}, "")
    assert bilibili.requests[-1].url.params["qrcode_key"] == ticket.key


async def test_confirmed_scan_returns_the_set_cookie_login(bilibili):
    api = BilibiliLoginApi(bilibili.transport)
    bilibili.scan_code = 0
    result = await api.poll_qrcode("key-1")
    assert result.state is QrScanState.SUCCESS
    assert result.cookies["SESSDATA"] == "sess%2C1%2Cabc"
    assert {"bili_jct", "DedeUserID"} <= set(result.cookies)
    assert result.refresh_token == "refresh"


async def test_confirmed_scan_without_session_cookie_fails():
    def handler(_request: httpx.Request) -> httpx.Response:
        data = {"code": 0, "refresh_token": "r", "url": "", "message": ""}
        return httpx.Response(200, json={"code": 0, "data": data})

    api = BilibiliLoginApi(httpx.MockTransport(handler))
    with pytest.raises(BilibiliApiError, match="SESSDATA"):
        await api.poll_qrcode("key")


async def test_unknown_scan_code_is_an_error_not_a_waiting_state():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": 0, "data": {"code": 12345}})

    with pytest.raises(BilibiliApiError, match="12345"):
        await BilibiliLoginApi(httpx.MockTransport(handler)).poll_qrcode("key")


async def test_nav_separates_valid_login_from_rejected_login(bilibili):
    api = BilibiliLoginApi(bilibili.transport)
    account = await api.fetch_account(dict(bilibili.login_cookies))
    assert account is not None
    assert (account.uid, account.uname) == (42, "主播")
    bilibili.login_valid = False
    assert await api.fetch_account(dict(bilibili.login_cookies)) is None


async def test_nav_failure_other_than_logged_out_is_raised():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": -412, "message": "请求被拦截"})

    with pytest.raises(BilibiliApiError, match="-412"):
        await BilibiliLoginApi(httpx.MockTransport(handler)).fetch_account({"a": "b"})
