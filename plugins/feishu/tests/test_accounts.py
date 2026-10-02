"""Saved Feishu applications: registration on load, saving, rules and orphans."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest
from shiori_sdk.accounts import AccountResponseRules
from shiori_sdk.testing.channel_context import FakeChannelPluginContext
from shiori_sdk.testing.storage import FakeKV

from plugins.feishu.backend import accounts as feishu_accounts
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


async def _load(kv: FakeKV, roles: set[str] | None = None) -> FakeChannelPluginContext:
    """Runs setup over saved plugin data, as one application start does."""
    ctx = FakeChannelPluginContext("feishu", PLUGIN_DIR)
    ctx.kv = kv
    ctx.accounts.available_roles = roles
    await setup(ctx.as_capability())
    return ctx


async def _unload(ctx: FakeChannelPluginContext) -> None:
    try:
        for group in ctx.channels.channels:
            await group.stop()
    finally:
        await ctx.aclose()


@pytest.mark.asyncio
async def test_saved_applications_register_separate_accounts_and_channels() -> None:
    kv = FakeKV()
    kv.set(
        "applications",
        [
            _app("cli_a"),
            _app("cli_b", "other", domain="lark", app_secret="${MISSING_SECRET}"),
            _app("cli_c", "third", connection_enabled=False),
        ],
    )
    ctx = await _load(kv)
    try:
        assert {
            account_id: snapshot.connection
            for account_id, snapshot in ctx.accounts.records.items()
        } == {
            "feishu:feishu:cli_a": "connecting",
            "feishu:lark:cli_b": "login_required",
            "feishu:feishu:cli_c": "offline",
        }
        # Only the application that can connect runs as a member channel.
        [group] = ctx.channels.channels
        assert group.member("feishu:cli_a") is not None
        assert group.member("lark:cli_b") is None
        assert group.member("feishu:cli_c") is None
    finally:
        await _unload(ctx)


@pytest.mark.asyncio
async def test_rules_survive_restart_and_apps_of_deleted_roles_are_purged() -> None:
    kv = FakeKV()
    kv.set("applications", [_app("cli_a"), _app("cli_gone", "deleted-role")])
    for key in ("profile", "targets"):
        kv.set(f"{key}:feishu:cli_gone", {"stale": True})
    rules = AccountResponseRules(private_enabled=False, blocked_sender_ids=("ou_x",))

    first = await _load(kv, {"mira"})
    try:
        # The application whose role is gone is deleted with its data.
        assert list(first.accounts.records) == ["feishu:feishu:cli_a"]
        applications = kv.get("applications")
        assert isinstance(applications, list)
        assert [row["app_id"] for row in applications] == ["cli_a"]
        assert kv.get("profile:feishu:cli_gone") is None
        assert kv.get("targets:feishu:cli_gone") is None
        assert first.accounts.rules_handler is not None
        first.accounts.rules_handler("feishu:cli_a", rules)
    finally:
        await _unload(first)

    restarted = await _load(kv, {"mira"})
    try:
        [snapshot] = restarted.accounts.records.values()
        assert snapshot.record.response_rules == rules
    finally:
        await _unload(restarted)


@pytest.mark.asyncio
async def test_saved_application_keeps_its_secret_for_its_role_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verify = AsyncMock(return_value={"name": "Bot", "open_id": "ou_bot"})
    monkeypatch.setattr(feishu_accounts, "verify_app", verify)
    kv = FakeKV()
    ctx = await _load(kv, {"mira", "other"})
    try:
        saved = await ctx.rpc.handlers["accounts.save"](
            {
                "role_id": "mira",
                "domain": "lark",
                "app_id": "cli_new",
                "app_secret": "new-secret",
            }
        )
        assert saved == {"account_id": "feishu:lark:cli_new"}
        verify.assert_awaited_once()
        applications = kv.get("applications")
        assert isinstance(applications, list)
        [stored] = applications
        assert (stored["app_secret"], stored["role_id"]) == ("new-secret", "mira")
        with pytest.raises(ValueError, match="另一个角色"):
            await ctx.rpc.handlers["accounts.save"](
                {"role_id": "other", "domain": "lark", "app_id": "cli_new"}
            )
    finally:
        await _unload(ctx)
