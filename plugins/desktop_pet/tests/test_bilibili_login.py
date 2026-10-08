"""QR login flow, live account status and engine credential access per role."""

import pytest
from shiori_sdk.role_events import RoleDeleted
from shiori_sdk.testing.roles import FakeRoles

from plugins.desktop_pet.backend.bilibili_api import BilibiliLoginApi
from plugins.desktop_pet.backend.bilibili_credentials import BilibiliCredentialStore
from plugins.desktop_pet.backend.bilibili_login import (
    BilibiliLoginRequired,
    BilibiliLoginService,
)


def _service(tmp_path, bilibili):
    roles = FakeRoles(tmp_path)
    roles.create_role(role_id="role", name="Role", system_prompt="Role")
    store = BilibiliCredentialStore(tmp_path)
    return (
        BilibiliLoginService(roles, store, BilibiliLoginApi(bilibili.transport)),
        roles,
        store,
    )


async def test_scan_confirm_success_persists_privately_and_logout_clears(
    tmp_path, bilibili
):
    service, roles, store = _service(tmp_path, bilibili)
    assert await service.status("role") == {"state": "logged_out"}
    started = await service.start("role")
    assert started["state"] == "waiting_scan"
    assert str(started["qrcode"]).startswith("data:image/png;base64,")
    assert await service.poll("role") == {"state": "waiting_scan"}
    bilibili.scan_code = 86090
    assert await service.poll("role") == {"state": "waiting_confirm"}
    bilibili.scan_code = 0
    account = {"uid": 42, "uname": "主播"}
    assert await service.poll("role") == {"state": "success", "account": account}
    saved = store.read("role")
    assert saved is not None and saved.cookies["SESSDATA"] == "sess%2C1%2Cabc"
    assert roles.extensions.values == {}
    assert await service.status("role") == {"state": "logged_in", "account": account}
    assert (await service.require_credentials("role")).cookies == saved.cookies
    with pytest.raises(ValueError, match="没有进行中"):
        await service.poll("role")

    assert service.logout("role") == {"state": "logged_out"}
    assert store.read("role") is None
    assert await service.status("role") == {"state": "logged_out"}
    with pytest.raises(BilibiliLoginRequired, match="尚未登录"):
        await service.require_credentials("role")


async def test_expired_qr_ends_the_attempt(tmp_path, bilibili):
    service, _roles, store = _service(tmp_path, bilibili)
    await service.start("role")
    bilibili.scan_code = 86038
    assert await service.poll("role") == {"state": "expired"}
    with pytest.raises(ValueError, match="没有进行中"):
        await service.poll("role")
    assert store.read("role") is None


async def test_rejected_login_reports_invalid_and_never_serves_credentials(
    tmp_path, bilibili
):
    service, _roles, store = _service(tmp_path, bilibili)
    await service.start("role")
    bilibili.scan_code = 0
    await service.poll("role")
    bilibili.login_valid = False
    assert await service.status("role") == {
        "state": "invalid",
        "account": {"uid": 42, "uname": "主播"},
    }
    with pytest.raises(BilibiliLoginRequired, match="已失效"):
        await service.require_credentials("role")
    assert store.read("role") is not None


async def test_logout_during_poll_discards_the_late_success(tmp_path, bilibili):
    service, _roles, store = _service(tmp_path, bilibili)
    await service.start("role")
    bilibili.scan_code = 0
    original = bilibili._poll

    def logout_mid_request():
        service.logout("role")
        return original()

    bilibili._poll = logout_mid_request
    with pytest.raises(ValueError, match="已被取消"):
        await service.poll("role")
    assert store.read("role") is None


async def test_unknown_role_is_rejected_and_deleted_role_loses_login(
    tmp_path, bilibili
):
    service, _roles, store = _service(tmp_path, bilibili)
    with pytest.raises(ValueError, match="不存在"):
        await service.start("missing")
    await service.start("role")
    bilibili.scan_code = 0
    await service.poll("role")
    await service.on_role_deleted(RoleDeleted(role_id="role"))
    assert store.read("role") is None
