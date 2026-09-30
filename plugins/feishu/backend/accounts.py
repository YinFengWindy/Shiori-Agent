"""Feishu application ownership, persistence, and connection lifecycle."""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.accounts import (
    AccountDeletionPlan,
    AccountResponseRules,
    response_rules_to_dict,
    stored_response_rules,
)
from infra.channels.account_group import AccountChannelGroup

from .channel import FeishuChannel
from .config import FeishuAppConfig, FeishuApplication, FeishuApplicationStore
from .formatting import CHANNEL
from .identity import verify_app

if TYPE_CHECKING:
    from agent.plugin_host.runtime_context import PluginRuntimeContext


class FeishuAccounts:
    """Saved applications, their host accounts and their member channels."""

    def __init__(self, ctx: PluginRuntimeContext, group: AccountChannelGroup) -> None:
        self._ctx = ctx
        self._group = group
        self._store = FeishuApplicationStore(ctx.kv)
        # Host account ID -> application ref, for account-scoped RPCs.
        self._refs: dict[str, str] = {}

    async def load(self) -> None:
        """Registers every saved application; deletes those whose role is gone."""
        for row in self._store.rows():
            try:
                app = FeishuApplication.model_validate(row)
                rules = stored_response_rules(app.response_rules)
            except ValueError as exc:
                ref = row.get("app_id") if isinstance(row, dict) else None
                self._ctx.accounts.reject(str(ref or "?"), str(exc))
                continue
            if app.role_id and not self._ctx.accounts.role_exists(app.role_id):
                self._store.remove(app.ref)
                continue
            profile = self._ctx.kv.get(f"profile:{app.ref}", {})
            snapshot = self._ctx.accounts.register_saved(
                platform="feishu",
                platform_account_id=app.ref,
                config_ref=app.ref,
                role_id=app.role_id or None,
                display_name=str(profile.get("name") or ""),
                avatar_url=str(profile.get("avatar") or ""),
                response_rules=rules,
            )
            if snapshot is None:
                continue
            self._refs[snapshot.record.id] = app.ref
            if app.connection_enabled:
                await self._connect(app, snapshot.record.id)
            else:
                self._ctx.accounts.report(snapshot.record.id, connection="offline")

    def ref_for_account(self, payload: dict[str, object]) -> str:
        """The application behind an account-scoped RPC's ``account_id``."""
        try:
            return self._refs[str(payload.get("account_id") or "")]
        except KeyError as exc:
            raise ValueError("飞书账号不存在") from exc

    def channel(self, ref: str) -> FeishuChannel | None:
        """The running member channel of one application, if connected."""
        channel = self._group.member(ref)
        return channel if isinstance(channel, FeishuChannel) else None

    def application(self, ref: str) -> FeishuApplication | None:
        """Returns one saved application for account-scoped queries."""
        return self._store.get(ref)

    async def _connect(self, app: FeishuApplication, account_id: str) -> None:
        secret = app.resolved_secret()
        if not secret:
            self._ctx.accounts.report(
                account_id,
                connection="login_required",
                error="App Secret 未配置或环境变量未解析",
            )
            return
        self._ctx.accounts.report(account_id, connection="connecting")
        await self._group.add(
            app.ref,
            FeishuChannel(
                app_id=app.app_id,
                app_secret=secret,
                domain=app.base_url,
                name=f"{CHANNEL}:{app.ref}",
                account_id=account_id,
                accounts=self._ctx.accounts,
                profile_store=self._ctx.kv,
                profile_ref=app.ref,
                role_id=app.role_id,
                chat_types=self._ctx.manifest.channel_chat_types(CHANNEL),
                avatars=self._ctx.avatars,
            ),
        )

    async def _retire(self, ref: str) -> None:
        """Stops an application's channel for good; later stops never report."""
        channel = await self._group.remove(ref)
        if isinstance(channel, FeishuChannel):
            await channel.retire()

    async def verify(self, app: FeishuAppConfig) -> dict[str, str]:
        """Authenticates credentials; a known app must still be the same bot."""
        identity = await verify_app(app)
        known = self._ctx.kv.get(f"profile:{app.ref}", {})
        known_id = str(known.get("open_id") or "")
        if known_id and known_id != identity["open_id"]:
            raise ValueError("应用凭据指向不同的机器人，请新建账号")
        return identity

    async def save(self, payload: dict[str, object]) -> dict[str, object]:
        """Saves (after verification) and connects an application for its role."""
        role_id = str(payload.get("role_id") or "").strip()
        draft = FeishuAppConfig.model_validate(payload)
        existing = self._store.get(draft.ref)
        if existing is not None and existing.role_id != role_id:
            raise ValueError("这个飞书应用已属于另一个角色")
        secret = draft.app_secret or (existing.app_secret if existing else "")
        if not secret:
            raise ValueError("请输入 App Secret")
        candidate = draft.model_copy(update={"app_secret": secret})
        if existing is None or draft.app_secret:
            await self.verify(candidate)
        self._ctx.accounts.check_owner(
            config_ref=draft.ref, role_id=role_id, platform_account_id=draft.ref
        )
        app = FeishuApplication(
            **candidate.model_dump(),
            connection_enabled=True,
            role_id=role_id,
            response_rules=existing.response_rules if existing else None,
        )
        self._store.save(app)
        profile = self._ctx.kv.get(f"profile:{app.ref}", {})
        snapshot = self._ctx.accounts.register(
            platform="feishu",
            platform_account_id=app.ref,
            config_ref=app.ref,
            role_id=role_id,
            display_name=str(profile.get("name") or "") or None,
            response_rules=stored_response_rules(app.response_rules),
        )
        account_id = snapshot.record.id
        self._refs[account_id] = app.ref
        await self._retire(app.ref)
        await self._connect(app, account_id)
        return {"account_id": account_id}

    async def disconnect(self, payload: dict[str, object]) -> dict[str, object]:
        """Stops one application and remembers to keep it offline."""
        ref = self.ref_for_account(payload)
        app = self._store.get(ref)
        if app is None:
            raise ValueError("飞书账号不存在")
        if app.role_id != str(payload.get("role_id") or "").strip():
            raise ValueError("这个飞书应用已属于另一个角色")
        self._store.save(app.model_copy(update={"connection_enabled": False}))
        await self._retire(ref)
        account_id = str(payload["account_id"])
        self._ctx.accounts.report(account_id, connection="offline")
        return {"account_id": account_id}

    def delete_plan(self, config_ref: str) -> AccountDeletionPlan:
        """Closes the WebSocket before purging so it cannot refill caches."""

        async def disconnect() -> None:
            await self._retire(config_ref)
            for account_id in [
                key for key, ref in self._refs.items() if ref == config_ref
            ]:
                del self._refs[account_id]

        async def purge() -> None:
            self._store.remove(config_ref)

        return AccountDeletionPlan(disconnect=disconnect, purge=purge)

    def save_rules(self, config_ref: str, rules: AccountResponseRules) -> None:
        """Persists host-edited response rules with the application."""
        app = self._store.get(config_ref)
        if app is None:
            raise KeyError(f"飞书账号不存在: {config_ref}")
        self._store.save(
            app.model_copy(update={"response_rules": response_rules_to_dict(rules)})
        )
