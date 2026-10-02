"""Feishu applications live in plugin storage; managed only through bridge requests."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from shiori_sdk.testing.bridge import PluginBridgeService, plugin_bridge_request

from core.roles.store import RoleStore

_RULES = {
    "private_enabled": False,
    "group_enabled": True,
    "blocked_sender_ids": ["ou_x"],
}


def _roles(root, *role_ids: str) -> None:
    roles = RoleStore(root)
    for role_id in role_ids:
        roles.create_role(role_id=role_id, name=role_id, system_prompt="m")


def _verified_bot(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("tenant_access_token/internal"):
        return httpx.Response(200, json={"code": 0, "tenant_access_token": "t"})
    return httpx.Response(
        200, json={"code": 0, "bot": {"app_name": "Bot", "open_id": "ou_bot"}}
    )


class _MockedClient(httpx.AsyncClient):
    """Answers every new client's Feishu calls offline with a verified bot."""

    def __init__(self, *args: Any, transport: Any = None, **kwargs: Any) -> None:
        super().__init__(
            *args, transport=transport or httpx.MockTransport(_verified_bot), **kwargs
        )


async def _save(
    service: PluginBridgeService, role_id: str, app_id: str
) -> dict[str, Any]:
    saved = await plugin_bridge_request(
        service,
        "plugin.feishu.accounts.save",
        {"role_id": role_id, "domain": "feishu", "app_id": app_id, "app_secret": "s"},
    )
    assert saved.error is None, saved.error
    return saved.payload


async def _set_enabled(service: PluginBridgeService, enabled: bool) -> None:
    toggled = await plugin_bridge_request(
        service,
        "plugins.setEnabled",
        {"plugin_id": "feishu", "enabled": enabled, "operation_id": f"f-{enabled}"},
    )
    assert toggled.error is None, toggled.error


@pytest.mark.asyncio
async def test_saved_app_never_touches_host_config_and_deletes_completely(
    plugin_runtime, tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", _MockedClient)
    _roles(tmp_path, "mira", "other")
    async with plugin_runtime(("feishu",)) as (service, path):
        config_before = path.read_text(encoding="utf-8")
        saved = await plugin_bridge_request(
            service,
            "plugin.feishu.accounts.save",
            {
                "role_id": "mira",
                "domain": "lark",
                "app_id": "cli_new",
                "app_secret": "new-secret",
            },
        )
        assert saved.error is None, saved.error
        assert saved.payload == {"account_id": "feishu:lark:cli_new"}
        refused = await plugin_bridge_request(
            service,
            "plugin.feishu.accounts.save",
            {"role_id": "other", "domain": "lark", "app_id": "cli_new"},
        )
        assert refused.error is not None and "另一个角色" in refused.error.message

        listed = await plugin_bridge_request(service, "accounts.list")
        [account] = listed.payload["accounts"]
        assert (account["id"], account["role_id"]) == ("feishu:lark:cli_new", "mira")
        assert path.read_text(encoding="utf-8") == config_before
        assert "new-secret" not in config_before

        deleted = await plugin_bridge_request(
            service,
            "accounts.delete",
            {"account_id": "feishu:lark:cli_new", "role_id": "mira"},
        )
        assert deleted.error is None, deleted.error
        after = await plugin_bridge_request(service, "accounts.list")
        assert after.payload["accounts"] == []
        assert path.read_text(encoding="utf-8") == config_before
        # Deleted completely: another role may now add the same application.
        readded = await plugin_bridge_request(
            service,
            "plugin.feishu.accounts.save",
            {
                "role_id": "other",
                "domain": "lark",
                "app_id": "cli_new",
                "app_secret": "s",
            },
        )
        assert readded.error is None, readded.error
        assert readded.payload == {"account_id": "feishu:lark:cli_new"}


@pytest.mark.asyncio
async def test_rules_survive_reload_and_apps_of_a_role_deleted_while_unloaded_go(
    plugin_runtime, tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", _MockedClient)
    _roles(tmp_path, "mira", "gone", "third")
    async with plugin_runtime(("feishu",)) as (service, _path):
        kept = (await _save(service, "mira", "cli_a"))["account_id"]
        await _save(service, "gone", "cli_gone")
        changed = await plugin_bridge_request(
            service,
            "accounts.rules.set",
            {"account_id": kept, "response_rules": _RULES},
        )
        assert changed.error is None, changed.error

        await _set_enabled(service, False)
        # The unloaded plugin is not asked to clean up the role's application.
        removed = await plugin_bridge_request(
            service, "roles.delete", {"role_id": "gone"}
        )
        assert removed.error is None, removed.error
        assert removed.payload["deleted_accounts"] == []
        await _set_enabled(service, True)

        listed = await plugin_bridge_request(service, "accounts.list")
        assert [
            (row["id"], row["response_rules"]) for row in listed.payload["accounts"]
        ] == [(kept, _RULES)]
        # The orphaned application was purged on load, so another role can add it.
        assert await _save(service, "third", "cli_gone") == {
            "account_id": "feishu:feishu:cli_gone"
        }
