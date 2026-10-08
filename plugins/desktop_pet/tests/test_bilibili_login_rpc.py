"""Bilibili login RPCs: QR-only entry, role-scoped, network calls off the mutation lane."""

import pytest
from shiori_sdk.rpc import Concurrency
from shiori_sdk.testing.memory_context import FakeRpc
from shiori_sdk.testing.roles import FakeRoles

from plugins.desktop_pet.backend.bilibili_api import BilibiliLoginApi
from plugins.desktop_pet.backend.bilibili_credentials import BilibiliCredentialStore
from plugins.desktop_pet.backend.bilibili_login import BilibiliLoginService
from plugins.desktop_pet.backend.bilibili_login_rpc import register_bilibili_login


async def test_rpcs_drive_qr_login_and_offer_no_cookie_entry(tmp_path, bilibili):
    roles = FakeRoles(tmp_path)
    roles.create_role(role_id="role", name="Role", system_prompt="Role")
    service = BilibiliLoginService(
        roles, BilibiliCredentialStore(tmp_path), BilibiliLoginApi(bilibili.transport)
    )
    rpc = FakeRpc()
    register_bilibili_login(rpc, service)
    assert set(rpc.handlers) == {
        "bilibili.login.start",
        "bilibili.login.poll",
        "bilibili.account.status",
        "bilibili.account.logout",
    }
    assert rpc.concurrency["bilibili.login.poll"] is Concurrency.INTEGRATION
    assert rpc.concurrency["bilibili.account.logout"] is Concurrency.MUTATION
    with pytest.raises(ValueError, match="role_id"):
        await rpc.handlers["bilibili.login.start"]({})

    await rpc.handlers["bilibili.login.start"]({"role_id": "role"})
    bilibili.scan_code = 0
    # Extra fields are ignored: cookies can only come from the confirmed scan.
    forged = {"role_id": "role", "cookies": {"SESSDATA": "forged"}}
    assert (await rpc.handlers["bilibili.login.poll"](forged))["state"] == "success"
    status = await rpc.handlers["bilibili.account.status"]({"role_id": "role"})
    assert status == {"state": "logged_in", "account": {"uid": 42, "uname": "主播"}}
    await rpc.handlers["bilibili.account.logout"]({"role_id": "role"})
    status = await rpc.handlers["bilibili.account.status"]({"role_id": "role"})
    assert status == {"state": "logged_out"}
