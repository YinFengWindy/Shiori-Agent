from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from shiori_plugin_testkit.bridge import plugin_bridge_request
from shiori_plugin_testkit.packages import stage_plugin_package

from agent.plugin_host import HostServices, PluginKernel, load_manifest
from agent.plugin_host.kv import PluginKVStore
from agent.plugin_host.plugin_data import plugin_data_dir
from bus.event_bus import EventBus
from core.accounts import AccountResponseRules, AccountSnapshot
from core.accounts.target_contract import UncertainDeliveryError
from core.roles.store import RoleStore
from plugins.feishu.backend.plugin import setup

PLUGIN_DIR = Path(__file__).resolve().parents[1]


def _app(app_id: str, role_id: str = "mira", **extra: Any) -> dict[str, Any]:
    return {
        "app_id": app_id,
        "app_secret": "secret",
        "domain": "feishu",
        "role_id": role_id,
        **extra,
    }


class _DictKV:
    """In-memory stand-in for the plugin KV capability."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.data[key] = value

    def delete(self, key: str) -> None:
        self.data.pop(key, None)


def _fake_ctx(kv: dict[str, Any], handlers: dict[str, Any], channels: list[Any]):
    return SimpleNamespace(
        kv=_DictKV(kv),
        rpc=SimpleNamespace(
            register=lambda name, handler, **kwargs: handlers.__setitem__(name, handler)
        ),
        accounts=SimpleNamespace(
            register_saved=lambda **kwargs: SimpleNamespace(
                record=SimpleNamespace(id="account-a")
            ),
            role_exists=lambda role_id: True,
            report=lambda *args, **kwargs: None,
            on_delete=lambda handler: handlers.__setitem__("delete", handler),
            on_rules_change=lambda handler: None,
        ),
        avatars=SimpleNamespace(),
        channels=SimpleNamespace(add=channels.append),
        manifest=SimpleNamespace(channel_chat_types=lambda name: ()),
    )


@pytest.mark.asyncio
async def test_shared_account_rpc_uses_selected_private_application() -> None:
    handlers: dict[str, Any] = {}
    channels: list[Any] = []
    kv = {"applications": [_app("cli_a")], "targets:feishu:cli_a": {"oc_chat": "u"}}
    await setup(_fake_ctx(kv, handlers, channels))
    assert (
        await handlers["account.targets"]({"account_id": "account-a", "kind": "known"})
    )["coverage"] == "observed_private_chats"
    [group] = channels
    member = group.member("feishu:cli_a")
    assert member.name == "feishu:feishu:cli_a"
    member.send = AsyncMock(return_value="om_9")
    request = {
        "account_id": "account-a",
        "target_kind": "private",
        "target_id": "oc_chat",
        "message": "hello",
    }
    assert await handlers["account.send"](request) == {
        "message_id": "om_9",
        "via_account": member.via_account(),
    }
    assert member.via_account()["platform_account_id"] == "feishu:cli_a"
    member.send.assert_awaited_once_with("oc_chat", "hello")
    member.send.return_value = None
    with pytest.raises(UncertainDeliveryError):
        await handlers["account.send"](request)
    member.send.side_effect = httpx.ReadTimeout("reply lost")
    with pytest.raises(UncertainDeliveryError):
        await handlers["account.send"](request)
    with pytest.raises(ValueError, match="私聊"):
        await handlers["account.send"](
            {"account_id": "account-a", "target_kind": "group"}
        )


@pytest.mark.asyncio
async def test_stored_bot_avatar_is_registered_on_load() -> None:
    avatar = "data:image/png;base64,iVBORw0KGgo="
    kv = {
        "applications": [_app("cli_a", connection_enabled=False)],
        "profile:feishu:cli_a": {"name": "Bot", "avatar": avatar},
    }
    ctx = _fake_ctx(kv, {}, [])
    registered: list[dict[str, Any]] = []
    ctx.accounts.register_saved = lambda **kwargs: registered.append(
        kwargs
    ) or SimpleNamespace(record=SimpleNamespace(id="account-a"))

    await setup(ctx)

    assert [row["avatar_url"] for row in registered] == [avatar]


@pytest.mark.asyncio
async def test_delete_hook_closes_the_websocket_before_purging() -> None:
    handlers: dict[str, Any] = {}
    channels: list[Any] = []
    kv: dict[str, Any] = {
        "applications": [_app("cli_a")],
        "profile:feishu:cli_a": {},
        "targets:feishu:cli_a": {},
    }
    await setup(_fake_ctx(kv, handlers, channels))
    [group] = channels
    channel = group.member("feishu:cli_a")
    order: list[str] = []
    channel.stop = AsyncMock(side_effect=lambda: order.append(f"stop:{len(kv)}"))

    plan = handlers["delete"]("feishu:cli_a")
    # Planning is side-effect free; disconnect closes before purge deletes.
    assert order == [] and len(kv) == 3
    await plan.disconnect()
    await plan.purge()
    assert order == ["stop:3"]
    assert kv == {"applications": []}
    assert channel._accounts is None
    repeated = handlers["delete"]("feishu:cli_a")
    await repeated.disconnect()
    await repeated.purge()
    assert channel.stop.await_count == 1


def test_manifest_declares_the_feishu_channel_for_binding_discovery() -> None:
    manifest = load_manifest(PLUGIN_DIR)

    assert manifest is not None
    assert manifest.display_name == "飞书"
    assert manifest.config_model is None
    [channel] = manifest.channels
    assert (channel.name, channel.label) == ("feishu", "飞书")
    # Private-only: there is no group blacklist whose member IDs need a label.
    assert channel.contact_label is None
    [private] = channel.chat_types
    assert (private.type, private.prefix) == ("private", None)
    assert (private.chat_id_hint or "").startswith("oc_")


def _load(root: Path, roles: RoleStore) -> tuple[list[Any], list[AccountSnapshot]]:
    """Loads the staged plugin once against ``root``, like one app start."""
    if not (root / "plugins" / "feishu").exists():
        stage_plugin_package(PLUGIN_DIR, root / "plugins" / "feishu")
    kernel = PluginKernel(
        [root / "plugins"],
        services=HostServices(event_bus=EventBus(), workspace=root, role_store=roles),
    )
    asyncio.run(kernel.load_all())
    [group] = kernel.channels
    return group, roles.accounts.list()


def _roles(root: Path, *role_ids: str) -> RoleStore:
    roles = RoleStore(root)
    for role_id in role_ids:
        if roles.get_role(role_id) is None:
            roles.create_role(role_id=role_id, name=role_id, system_prompt="m")
    return roles


def test_saved_applications_register_separate_accounts_and_channels(
    tmp_path,
) -> None:
    kv = PluginKVStore(plugin_data_dir(tmp_path, "feishu") / "kv.json")
    kv.set(
        "applications",
        [
            _app("cli_a"),
            _app("cli_b", "other", domain="lark", app_secret="${MISSING_SECRET}"),
            _app("cli_c", "third", connection_enabled=False),
        ],
    )
    group, accounts = _load(tmp_path, _roles(tmp_path, "mira", "other", "third"))
    assert {row.record.id: row.connection for row in accounts} == {
        "feishu:feishu:cli_a": "connecting",
        "feishu:lark:cli_b": "login_required",
        "feishu:feishu:cli_c": "offline",
    }
    assert group.member_channel("feishu:feishu:cli_a") is not None
    assert group.member("lark:cli_b") is None and group.member("feishu:cli_c") is None


def test_rules_survive_restart_and_orphaned_apps_are_deleted_on_load(
    tmp_path,
) -> None:
    kv = PluginKVStore(plugin_data_dir(tmp_path, "feishu") / "kv.json")
    kv.set("applications", [_app("cli_a"), _app("cli_gone", "deleted-role")])
    for key in ("profile", "targets"):
        kv.set(f"{key}:feishu:cli_gone", {"stale": True})
    roles = _roles(tmp_path, "mira")
    _group, [account] = _load(tmp_path, roles)
    # The app whose role is gone is deleted with its data, not served.
    assert [row["app_id"] for row in kv.get("applications")] == ["cli_a"]
    assert kv.get("profile:feishu:cli_gone") is None
    assert kv.get("targets:feishu:cli_gone") is None

    rules = AccountResponseRules(private_enabled=False, blocked_sender_ids=("ou_x",))
    roles.accounts.set_response_rules(account.record.id, rules)

    _group, [restarted] = _load(tmp_path, RoleStore(tmp_path))
    assert restarted.record.id == "feishu:feishu:cli_a"
    assert restarted.record.response_rules == rules


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
        kv = PluginKVStore(plugin_data_dir(tmp_path, "feishu") / "kv.json")
        [stored] = kv.get("applications")
        assert stored["app_secret"] == "new-secret"
        kv.set("profile:lark:cli_new", {"name": "Bot"})

        deleted = await plugin_bridge_request(
            service,
            "accounts.delete",
            {"account_id": "feishu:lark:cli_new", "role_id": "mira"},
        )
        assert deleted.error is None, deleted.error
        after = await plugin_bridge_request(service, "accounts.list")
        assert after.payload["accounts"] == []
        assert kv.get("applications") == []
        assert kv.get("profile:lark:cli_new") is None
        assert path.read_text(encoding="utf-8") == config_before
        assert "new-secret" not in config_before
