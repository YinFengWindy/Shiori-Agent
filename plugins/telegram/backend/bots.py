"""Telegram Bot accounts: saved in plugin storage, connected without a reload."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from core.accounts import (
    AccountDeletionPlan,
    AccountResponseRules,
    response_rules_to_dict,
    stored_response_rules,
)

from .credentials import (
    TelegramBotStore,
    resolve_token,
    valid_ref,
    verify_bot_token,
)

if TYPE_CHECKING:
    from agent.plugin_host.runtime_context import PluginRuntimeContext
    from infra.channels.account_group import AccountChannelGroup

    from .channel.lifecycle import TelegramChannel

_PLATFORM = "telegram"


class TelegramBots:
    """Registers saved Bots and runs each as a member channel ``telegram_<ref>``."""

    def __init__(
        self,
        ctx: PluginRuntimeContext,
        store: TelegramBotStore,
        group: AccountChannelGroup,
    ) -> None:
        self._ctx = ctx
        self._accounts = ctx.accounts
        self._store = store
        self._group = group
        # Registered host account ID per Bot ref.
        self._account_ids: dict[str, str] = {}

    async def load(self) -> None:
        """Registers every saved Bot; a Bot of a deleted role is deleted with its data."""
        for row in self._store.list():
            ref = str(row.get("ref") or "")
            role_id = str(row.get("role_id") or "") or None
            bot_id = str(row.get("bot_id") or "")
            if not valid_ref(ref) or not bot_id.isdigit():
                self._accounts.reject(ref or "?", "Bot 数据无效")
                continue
            if role_id is not None and not self._accounts.role_exists(role_id):
                self._store.remove(ref)
                continue
            try:
                rules = stored_response_rules(row.get("response_rules"))
            except ValueError as exc:
                self._accounts.reject(ref, str(exc))
                continue
            snapshot = self._accounts.register_saved(
                platform=_PLATFORM,
                platform_account_id=bot_id,
                config_ref=ref,
                role_id=role_id,
                response_rules=rules,
            )
            if snapshot is None:
                continue
            self._account_ids[ref] = snapshot.record.id
            await self._attach(row)

    async def _attach(self, row: dict[str, Any]) -> None:
        """Adds an enabled Bot's channel to the group; reports why it cannot run."""
        from telegram.error import InvalidToken

        from .channel import TelegramChannel

        ref = row["ref"]
        account_id = self._account_ids[ref]
        if not row.get("enabled", True):
            self._accounts.report(account_id, connection="offline")
            return
        token = resolve_token(str(row.get("token") or ""))
        if not token:
            self._accounts.report(
                account_id,
                connection="login_required",
                error="Bot Token 未配置或环境变量未解析",
            )
            return
        try:
            channel = TelegramChannel(
                token=token,
                name=f"telegram_{ref}",
                config_ref=ref,
                accounts=self._accounts,
                known_store=self._ctx.kv,
                role_id=row["role_id"],
                chat_types=self._ctx.manifest.channel_chat_types(_PLATFORM),
            )
        except InvalidToken:
            self._accounts.report(
                account_id, connection="login_required", error="Invalid Bot Token"
            )
            return
        channel._account_id = account_id
        await self._group.add(ref, channel)

    def channel(self, ref: str) -> TelegramChannel | None:
        """The running channel of one Bot, if connected."""
        return cast("TelegramChannel | None", self._group.member(ref))

    def ref_for_account(self, account_id: str) -> str:
        """Resolves a host account ID to its Bot ref."""
        for ref, known in self._account_ids.items():
            if account_id and known == account_id:
                return ref
        raise ValueError("Unknown Telegram Bot account")

    def _owned_ref(self, payload: dict[str, Any]) -> str:
        ref = self.ref_for_account(str(payload.get("account_id") or ""))
        if self._store.get(ref).get("role_id") != str(payload.get("role_id") or ""):
            raise ValueError("这个 Bot 已属于另一个角色")
        return ref

    async def save(self, payload: dict[str, Any]) -> dict[str, str]:
        """Adds a Bot for ``role_id``, or updates and reconnects one it owns."""
        role_id = str(payload.get("role_id") or "").strip()
        token = str(payload.get("token") or "").strip()
        if payload.get("account_id"):
            ref = self._owned_ref(payload)
            row = {**self._store.get(ref), "enabled": True}
            if token:
                identity = await verify_bot_token({"token": token})
                if identity["bot_id"] != row["bot_id"]:
                    raise ValueError("新 Token 属于另一个 Bot，请添加新账号")
                row["token"] = token
        else:
            if not token:
                raise ValueError("新账号需要 Bot Token")
            bot_id = (await verify_bot_token({"token": token}))["bot_id"]
            if any(
                bot_id in (item.get("bot_id"), item.get("ref"))
                for item in self._store.list()
            ):
                raise ValueError("此 Bot 已添加")
            # A new Bot is keyed by its identity, so re-adding it reuses its channel.
            ref = bot_id
            self._accounts.check_owner(
                config_ref=ref, role_id=role_id, platform_account_id=bot_id
            )
            row = {
                "ref": ref,
                "bot_id": bot_id,
                "token": token,
                "enabled": True,
                "role_id": role_id,
            }
        self._store.save(row)
        snapshot = self._accounts.register(
            platform=_PLATFORM,
            platform_account_id=row["bot_id"],
            config_ref=ref,
            role_id=role_id,
        )
        self._account_ids[ref] = snapshot.record.id
        _ = await self._group.remove(ref)
        await self._attach(row)
        return {"account_id": snapshot.record.id}

    async def disconnect(self, payload: dict[str, Any]) -> dict[str, str]:
        """Stops a Bot the role owns; it stays saved and listed offline."""
        ref = self._owned_ref(payload)
        self._store.save({**self._store.get(ref), "enabled": False})
        _ = await self._group.remove(ref)
        self._accounts.report(self._account_ids[ref], connection="offline")
        return {"account_id": self._account_ids[ref]}

    def save_rules(self, ref: str, rules: AccountResponseRules) -> None:
        """Persists host-edited response rules with the Bot record."""
        self._store.save(
            {**self._store.get(ref), "response_rules": response_rules_to_dict(rules)}
        )

    def delete_plan(self, ref: str) -> AccountDeletionPlan:
        """Stops polling before the record, Token and caches are purged."""

        async def disconnect() -> None:
            # Removed from the group, the stopped channel never runs again.
            _ = await self._group.remove(ref)
            self._account_ids.pop(ref, None)

        async def purge() -> None:
            self._store.remove(ref)

        return AccountDeletionPlan(disconnect=disconnect, purge=purge)
