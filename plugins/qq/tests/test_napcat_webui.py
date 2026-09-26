"""QQ QR status from the authenticated NapCat WebUI."""

from __future__ import annotations

import pytest

from plugins.qq.backend.napcat_webui import NapCatWebUi


@pytest.mark.asyncio
async def test_qr_status_never_claims_online_before_login(monkeypatch):
    webui = NapCatWebUi(lambda _ref: {})
    monkeypatch.setattr(
        webui,
        "_request",
        lambda _ref, route, _body: (
            {"isLogin": False, "qrcodeurl": "data:image/png;base64,QR"}
            if route == "CheckLoginStatus"
            else {"qrcodeurl": "data:image/png;base64,NEW"}
        ),
    )
    assert (await webui.login_status("a"))["phase"] == "login_required"
    assert (await webui.refresh_qrcode("a"))["qrcode"].endswith("NEW")
