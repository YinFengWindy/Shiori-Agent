import json
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from shiori_sdk.accounts import AccountResponseRules, account_id_for
from shiori_sdk.accounts.conversation import AccountConversation
from shiori_sdk.testing.channel_context import (
    FakeChannelPluginContext,
    fake_channel_context,
)
from plugins.grok_bot.backend.accounts import GrokAccounts
from plugins.grok_bot.backend.connection import GrokConnection
from plugins.grok_bot.backend.config import ConnectionConfig
from plugins.grok_bot.backend.store import ConnectionStore
from plugins.grok_bot.backend.protocol import BotMessage


async def test_multiple_roles_isolate_credentials_pause_rules_reload_and_delete(
    tmp_path, config, monkeypatch
):
    ctx = FakeChannelPluginContext("grok_bot", Path(__file__).resolve().parents[1])
    ctx.workspace = tmp_path
    group = ctx.channels.group("grok_bot")
    accounts = GrokAccounts(ctx, group)
    one = config.model_copy(update={"verified": True})
    two = config.model_copy(
        update={
            "connection_id": uuid4().hex,
            "peer_id": uuid4().hex,
            "role_id": "other",
            "callback_token": "other-token-" + uuid4().hex,
            "verified": True,
        }
    )
    store = ConnectionStore(ctx.kv)
    store.save(one)
    store.save(two)
    await accounts.load()
    await group.start(fake_channel_context(tmp_path))
    try:
        assert len(group.member_channels()) == 2
        first, second = (
            accounts.connections[value.connection_id] for value in (one, two)
        )
        assert first.client_file != second.client_file
        assert first.callback_url != second.callback_url
        detail = await accounts.detail({"account_id": first.account_id})
        assert config.callback_token not in json.dumps(detail)
        assert config.webhook_key not in json.dumps(detail)
        with pytest.raises(ValueError, match="另一个角色"):
            await accounts.disconnect(
                {"account_id": first.account_id, "role_id": "other"}
            )
        accounts.save_rules(
            one.connection_id,
            AccountResponseRules(private_enabled=False, allow_full_tools=True),
        )
        await accounts.disconnect({"account_id": first.account_id, "role_id": "mira"})
        assert not first.client_file.exists()
        assert second.client_file.exists()
        assert store.get(one.connection_id).enabled is False
        assert store.get(one.connection_id).response_rules["private_enabled"] is False
        assert store.get(one.connection_id).response_rules["allow_full_tools"] is True
        assert not (store.get(two.connection_id).response_rules or {}).get(
            "allow_full_tools", False
        )
        assert "full_tools" in ctx.accounts.records[first.account_id].capabilities
        restored = GrokAccounts(ctx, ctx.channels.group("grok_bot"))
        await restored.load()
        assert ctx.accounts.records[
            first.account_id
        ].record.response_rules.allow_full_tools
        restored.save_rules(one.connection_id, AccountResponseRules())
        assert not store.get(one.connection_id).response_rules.get(
            "allow_full_tools", False
        )
        plan = accounts.delete_plan(two.connection_id)
        await plan.disconnect()
        await plan.purge()
        assert not second.client_file.exists()
        assert two.connection_id not in store.rows()
    finally:
        await group.stop()
        await ctx.aclose()


async def test_save_keeps_secret_reference_and_stable_identity_but_rotates_new_bot(
    tmp_path, config, monkeypatch
):
    ctx = FakeChannelPluginContext("grok_bot", Path(__file__).resolve().parents[1])
    ctx.workspace = tmp_path
    ctx.config.references["${GROK_SECRET}"] = "resolved-secret"
    group = ctx.channels.group("grok_bot")
    accounts = GrokAccounts(ctx, group)
    monkeypatch.setattr(GrokConnection, "probe", AsyncMock())
    await group.start(fake_channel_context(tmp_path))
    try:
        result = await accounts.save(
            {
                "role_id": "mira",
                "webhook_url": config.webhook_url,
                "webhook_key": "${GROK_SECRET}",
            }
        )
        [original] = accounts.configs.values()
        original_route = AccountConversation(original.channel_name, original.chat_id)
        assert (
            ctx.accounts.records[result["account_id"]].tool_conversation
            == original_route
        )
        accounts.save_rules(
            original.connection_id, AccountResponseRules(allow_full_tools=True)
        )
        await accounts.disconnect({**result, "role_id": "mira"})
        await accounts.save(
            {**result, "role_id": "mira", "webhook_url": config.webhook_url}
        )
        [resumed] = accounts.configs.values()
        assert resumed.connection_id == original.connection_id
        assert resumed.peer_id == original.peer_id
        assert resumed.webhook_key == "${GROK_SECRET}"
        assert resumed.response_rules["allow_full_tools"] is True
        assert (
            ctx.accounts.records[result["account_id"]].tool_conversation
            == original_route
        )
        await accounts.save(
            {**result, "role_id": "mira", "webhook_url": "https://example.test/other"}
        )
        [changed] = accounts.configs.values()
        assert changed.connection_id == original.connection_id
        assert changed.peer_id != original.peer_id
        assert changed.callback_token != original.callback_token
        assert changed.verified is False
        assert not changed.response_rules.get("allow_full_tools", False)
        assert ctx.accounts.records[
            result["account_id"]
        ].tool_conversation == AccountConversation(
            changed.channel_name, changed.chat_id
        )
        assert (
            ctx.accounts.records[result["account_id"]].tool_conversation
            != original_route
        )
        accounts.save_rules(
            changed.connection_id, AccountResponseRules(allow_full_tools=True)
        )
        accounts._register(accounts.configs[changed.connection_id])
        assert ctx.accounts.records[
            result["account_id"]
        ].record.response_rules.allow_full_tools
        assert (
            ctx.accounts.records[result["account_id"]].tool_conversation
            != original_route
        )
    finally:
        await group.stop()
        await ctx.aclose()


async def test_deleted_role_and_corrupt_record_do_not_restore_other_accounts(
    tmp_path, config
):
    ctx = FakeChannelPluginContext("grok_bot", Path(__file__).resolve().parents[1])
    ctx.workspace = tmp_path
    ctx.accounts.available_roles = {"other"}
    store = ConnectionStore(ctx.kv)
    store.save(config)
    ctx.kv.set("connections", {**store.rows(), "broken": {"webhook_key": "do-not-log"}})
    accounts = GrokAccounts(ctx, ctx.channels.group("grok_bot"))
    try:
        await accounts.load()
        assert config.connection_id not in store.rows()
        assert not accounts.connections
        assert (
            account_id_for("grok_bot", config.connection_id) not in ctx.accounts.records
        )
    finally:
        await ctx.aclose()


@pytest.mark.parametrize("failed_step", ["journal", "client_file", "record"])
async def test_delete_plan_can_be_recreated_after_each_cleanup_failure(
    tmp_path: Path,
    config: ConnectionConfig,
    monkeypatch: pytest.MonkeyPatch,
    failed_step: str,
) -> None:
    ctx = FakeChannelPluginContext("grok_bot", Path(__file__).resolve().parents[1])
    ctx.workspace = tmp_path
    accounts = GrokAccounts(ctx, ctx.channels.group("grok_bot"))
    accounts.store.save(config.model_copy(update={"enabled": False}))
    await accounts.load()
    journal_key = f"exchange:{config.connection_id}:{config.peer_id}"
    ctx.kv.set(journal_key, {"pending": "stale transport state"})
    client_file = accounts.data_dir / config.connection_id / "client.json"
    client_file.parent.mkdir(parents=True)
    client_file.write_text("{}", encoding="utf-8")
    failed = False

    def fail_once() -> None:
        nonlocal failed
        if not failed:
            failed = True
            raise OSError("cleanup unavailable")

    if failed_step == "journal":
        delete = ctx.kv.delete

        def delete_journal(key: str) -> None:
            if key == journal_key:
                fail_once()
            delete(key)

        monkeypatch.setattr(ctx.kv, "delete", delete_journal)
    elif failed_step == "client_file":
        unlink = Path.unlink

        def unlink_client(path: Path, missing_ok: bool = False) -> None:
            if path == client_file:
                fail_once()
            unlink(path, missing_ok=missing_ok)

        monkeypatch.setattr(Path, "unlink", unlink_client)
    else:
        remove = accounts.store.remove

        def remove_record(connection_id: str) -> None:
            fail_once()
            remove(connection_id)

        monkeypatch.setattr(accounts.store, "remove", remove_record)

    try:
        plan = accounts.delete_plan(config.connection_id)
        await plan.disconnect()
        with pytest.raises(OSError, match="cleanup unavailable"):
            await plan.purge()
        assert config.connection_id in accounts.store.rows()
        assert config.connection_id in accounts.configs

        retry = accounts.delete_plan(config.connection_id)
        await retry.disconnect()
        await retry.purge()
        assert config.connection_id not in accounts.store.rows()
        assert config.connection_id not in accounts.configs
        assert ctx.kv.get(journal_key) is None
        assert not client_file.exists()

        # The host may request a new plan even after plugin data is already gone.
        ctx.accounts.records.pop(account_id_for("grok_bot", config.connection_id))
        completed = accounts.delete_plan(config.connection_id)
        await completed.disconnect()
        await completed.purge()
    finally:
        await ctx.aclose()


async def test_reconnect_keeps_all_inflight_send_receipts_and_reply_correlation(
    tmp_path: Path, config: ConnectionConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = FakeChannelPluginContext("grok_bot", Path(__file__).resolve().parents[1])
    ctx.workspace = tmp_path
    group = ctx.channels.group("grok_bot")
    accounts = GrokAccounts(ctx, group)
    accounts.store.save(config.model_copy(update={"verified": True}))
    await accounts.load()
    await group.start(fake_channel_context(tmp_path))
    old = accounts.connections[config.connection_id]
    entered, release = asyncio.Event(), asyncio.Event()

    async def delayed_post(payload: dict[str, object]) -> None:
        entered.set()
        await release.wait()

    monkeypatch.setattr(old._transport, "post", delayed_post)
    monkeypatch.setattr(GrokConnection, "probe", AsyncMock())
    tasks: list[asyncio.Task[dict[str, object]]] = []
    try:
        async with asyncio.timeout(5):
            tasks.append(asyncio.create_task(old.send(BotMessage("out-1", "first"))))
            await entered.wait()
            tasks.append(asyncio.create_task(old.send(BotMessage("out-2", "second"))))
            await asyncio.sleep(0)
            tasks.append(
                asyncio.create_task(
                    accounts.save(
                        {"role_id": config.role_id, "webhook_url": config.webhook_url}
                    )
                )
            )
            while group.member(config.connection_id) is not None:
                await asyncio.sleep(0)
            release.set()
            await asyncio.gather(*tasks)
        current = accounts.connections[config.connection_id]
        assert current is not old
        assert current.journal.state.count == 2
        assert {
            key: value.state for key, value in current.journal.state.messages.items()
        } == {"out-1": "accepted", "out-2": "accepted"}
        # Correlation to the second real send survives the handover too.
        assert current.journal.begin(BotMessage("reply", "received", "out-2"), "in", 12)
    finally:
        release.set()
        await asyncio.gather(*tasks, return_exceptions=True)
        await group.stop()
        await ctx.aclose()


async def test_reconnect_validates_credentials_before_retiring_and_restores_on_failure(
    tmp_path: Path, config: ConnectionConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = FakeChannelPluginContext("grok_bot", Path(__file__).resolve().parents[1])
    ctx.workspace = tmp_path
    group = ctx.channels.group("grok_bot")
    accounts = GrokAccounts(ctx, group)
    accounts.store.save(config.model_copy(update={"verified": True}))
    await accounts.load()
    await group.start(fake_channel_context(tmp_path))
    old = accounts.connections[config.connection_id]
    try:
        with pytest.raises(ValueError, match="未解析"):
            await accounts.save(
                {"role_id": config.role_id, "webhook_key": "${MISSING}"}
            )
        assert group.member(config.connection_id) is old
        assert old.client_file.exists()

        def failed_connection(
            candidate: ConnectionConfig, secret: str
        ) -> GrokConnection:
            raise ValueError("journal unavailable")

        monkeypatch.setattr(accounts, "_make_connection", failed_connection)
        with pytest.raises(ValueError, match="journal unavailable"):
            await accounts.save({"role_id": config.role_id})
        assert group.member(config.connection_id) is old
        assert old.status()["connected"]
        assert old.client_file.exists()
        assert accounts.store.get(config.connection_id).verified
        with pytest.raises(ValueError, match="journal unavailable"):
            await accounts.save(
                {
                    "role_id": "other",
                    "webhook_url": config.webhook_url,
                    "webhook_key": config.webhook_key,
                }
            )
        assert len(accounts.configs) == 1
    finally:
        await group.stop()
        await ctx.aclose()
