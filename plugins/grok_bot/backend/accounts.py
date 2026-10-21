"""Role ownership, persistent settings and independent connection lifecycle."""

import asyncio
import os
from secrets import token_urlsafe
from uuid import uuid4

from shiori_sdk.accounts import (
    AccountDeletionPlan,
    AccountResponseRules,
    ConnectionState,
    account_id_for,
    response_rules_to_dict,
    stored_response_rules,
)
from shiori_sdk.channels.context import ChannelPluginContext
from shiori_sdk.channels.group import AccountChannelGroup
from shiori_sdk.storage import plugin_data_dir

from .config import CHANNEL, ConnectionConfig, read_connection
from .connection import GrokConnection
from .exchange import ExchangeJournal
from .store import ConnectionStore


class GrokAccounts:
    """Own one fixed Bot binding per role and expose account-scoped operations."""

    def __init__(self, ctx: ChannelPluginContext, group: AccountChannelGroup) -> None:
        self.ctx = ctx
        self.group = group
        self.store = ConnectionStore(ctx.kv)
        self.data_dir = plugin_data_dir(ctx.workspace, CHANNEL)
        self.client_path = ctx.plugin_dir / (
            "client.ps1" if os.name == "nt" else "backend/client.py"
        )
        self.configs: dict[str, ConnectionConfig] = {}
        self.connections: dict[str, GrokConnection] = {}
        self._mutating = asyncio.Lock()

    def _register(self, config: ConnectionConfig, *, saved: bool = False) -> bool:
        register = (
            self.ctx.accounts.register_saved if saved else self.ctx.accounts.register
        )
        return (
            register(
                platform=CHANNEL,
                platform_account_id=config.connection_id,
                config_ref=config.connection_id,
                role_id=config.role_id,
                display_name=config.peer_name,
                response_rules=stored_response_rules(config.response_rules),
            )
            is not None
        )

    def _changed(self, config: ConnectionConfig) -> None:
        self.store.save(config)
        self.configs[config.connection_id] = config

    def _report(
        self, connection_id: str, state: ConnectionState, error: str = ""
    ) -> None:
        self.ctx.accounts.report(
            account_id_for(CHANNEL, connection_id),
            connection=state,
            error=error,
            capabilities=(
                frozenset({"private", "known_targets", "send"})
                if state == "online"
                else frozenset()
            ),
        )

    def _resolve_key(self, config: ConnectionConfig) -> str:
        secret = self.ctx.config.resolve_reference(config.webhook_key)
        if not secret or secret.startswith("${"):
            raise ValueError("Webhook 密钥未配置或环境变量未解析")
        return secret

    def _make_connection(self, config: ConnectionConfig, secret: str) -> GrokConnection:
        return GrokConnection(
            config,
            self.ctx.kv,
            self.data_dir,
            self.client_path,
            config_changed=self._changed,
            status_changed=lambda state, error: self._report(
                config.connection_id, state, error
            ),
            webhook_key=secret,
        )

    async def load(self) -> None:
        """Restore valid independent accounts; reject corrupt records individually."""
        for connection_id, row in self.store.rows().items():
            try:
                config = read_connection(row)
                if connection_id != config.connection_id:
                    raise ValueError("连接标识不匹配")
                if not self.ctx.accounts.role_exists(config.role_id):
                    self._purge(config)
                    continue
                if not self._register(config, saved=True):
                    continue
                self.configs[connection_id] = config
                if config.enabled:
                    connection = self._make_connection(
                        config, self._resolve_key(config)
                    )
                    self.connections[connection_id] = connection
                    await self.group.add(connection_id, connection)
                else:
                    self._report(connection_id, "offline")
            except ValueError as error:
                self.ctx.accounts.reject(connection_id, str(error))

    def _config_for(self, payload: dict[str, object]) -> ConnectionConfig:
        account_id = str(payload.get("account_id") or "")
        config = next(
            (
                row
                for key, row in self.configs.items()
                if account_id_for(CHANNEL, key) == account_id
            ),
            None,
        )
        if config is None:
            raise ValueError("Grok 连接不存在")
        if "role_id" in payload and payload["role_id"] != config.role_id:
            raise ValueError("Grok 连接属于另一个角色")
        return config

    async def save(self, payload: dict[str, object]) -> dict[str, object]:
        """Validate ownership before replacing a role's saved connection."""
        async with self._mutating:
            role_id = str(payload.get("role_id") or "").strip()
            previous = next(
                (row for row in self.configs.values() if row.role_id == role_id), None
            )
            if payload.get("account_id") and self._config_for(payload) != previous:
                raise ValueError("Grok 连接与角色不匹配")
            connection_id = previous.connection_id if previous else uuid4().hex
            self.ctx.accounts.check_owner(
                config_ref=connection_id,
                role_id=role_id,
                platform_account_id=connection_id,
            )
            url = payload.get("webhook_url", previous.webhook_url if previous else "")
            same_peer = previous is not None and url == previous.webhook_url
            config = read_connection(
                {
                    **(previous.model_dump() if previous else {}),
                    "connection_id": connection_id,
                    "peer_id": (
                        previous.peer_id
                        if previous is not None and same_peer
                        else uuid4().hex
                    ),
                    "role_id": role_id,
                    "webhook_url": url,
                    "webhook_key": payload.get("webhook_key")
                    or (previous.webhook_key if previous else ""),
                    "callback_token": (
                        previous.callback_token
                        if previous is not None and same_peer
                        else token_urlsafe(32)
                    ),
                    "enabled": True,
                    "verified": False,
                    "max_messages": payload.get(
                        "max_messages", previous.max_messages if previous else 12
                    ),
                }
            )
            secret = self._resolve_key(config)
            old = self.connections.get(connection_id)
            await self.group.remove(connection_id)
            try:
                # Read the persisted journal only after all old sends have drained.
                candidate = self._make_connection(config, secret)
                self._register(config)
                self._changed(config)
                self.connections[connection_id] = candidate
                await self.group.add(connection_id, candidate)
            except Exception:
                await self.group.remove(connection_id)
                self.connections.pop(connection_id, None)
                if previous is not None:
                    self._changed(previous)
                    self._register(previous)
                    if old is not None:
                        self.connections[connection_id] = old
                        await self.group.add(connection_id, old)
                elif connection_id in self.configs:
                    self._report(connection_id, "error", "回程监听启动失败")
                raise
            if previous is not None and previous.peer_id != config.peer_id:
                ExchangeJournal.purge_saved(
                    self.ctx.kv, previous.connection_id, previous.peer_id
                )
            try:
                await candidate.probe()
            except Exception:
                candidate.last_error = (
                    "连接验证未能完成，请检查 Webhook、密钥与 Bot 的本地执行能力"
                )
                self._report(connection_id, "error", candidate.last_error)
            return {"account_id": account_id_for(CHANNEL, connection_id)}

    async def _disconnect(self, connection_id: str) -> None:
        await self.group.remove(connection_id)
        self.connections.pop(connection_id, None)
        self._report(connection_id, "offline")

    async def disconnect(self, payload: dict[str, object]) -> dict[str, object]:
        """Pause one role's connection persistently without affecting other roles."""
        async with self._mutating:
            config = self._config_for(payload)
            await self._disconnect(config.connection_id)
            self._changed(
                self.configs[config.connection_id].model_copy(update={"enabled": False})
            )
            return {"account_id": account_id_for(CHANNEL, config.connection_id)}

    def _purge(self, config: ConnectionConfig) -> None:
        # Keep the binding until every cleanup succeeds so a new plan can retry.
        ExchangeJournal.purge_saved(self.ctx.kv, config.connection_id, config.peer_id)
        (self.data_dir / config.connection_id / "client.json").unlink(missing_ok=True)
        self.store.remove(config.connection_id)
        self.configs.pop(config.connection_id, None)

    def delete_plan(self, config_ref: str) -> AccountDeletionPlan:
        """Stop callbacks before removing credentials and transport state."""
        config = self.configs.get(config_ref)
        if config is None:
            rows = self.store.rows()
            if config_ref in rows:
                config = read_connection(rows[config_ref])

        async def disconnect() -> None:
            if config is not None:
                await self._disconnect(config_ref)

        async def purge() -> None:
            if config is not None:
                self._purge(config)

        return AccountDeletionPlan(disconnect=disconnect, purge=purge)

    def save_rules(self, config_ref: str, rules: AccountResponseRules) -> None:
        """Keep the host's response rules through reloads."""
        config = self.configs[config_ref].model_copy(
            update={"response_rules": response_rules_to_dict(rules)}
        )
        self._changed(config)
        if connection := self.connections.get(config_ref):
            connection.config = config

    async def detail(self, payload: dict[str, object]) -> dict[str, object]:
        """Return settings and real transport state without disclosing secrets."""
        config = self._config_for(payload)
        connection = self.connections.get(config.connection_id)
        journal = (
            connection.journal
            if connection
            else ExchangeJournal(self.ctx.kv, config.connection_id, config.peer_id)
        )
        return {
            "webhook_url": config.webhook_url,
            "has_key": bool(config.webhook_key),
            "enabled": config.enabled,
            "verified": config.verified,
            "max_messages": config.max_messages,
            "exchange_count": journal.state.count,
            "last_status": (connection.last_error if connection else "")
            or journal.state.last_status,
            "client_path": str(self.client_path),
            "connection_file": str(
                self.data_dir / config.connection_id / "client.json"
            ),
        }

    def connection_for(self, payload: dict[str, object]) -> GrokConnection:
        """Resolve only the account selected by the host's delivery service."""
        config = self._config_for(payload)
        connection = self.connections.get(config.connection_id)
        if connection is None:
            raise ValueError("Grok 连接已暂停")
        return connection

    async def reset_exchange(self, payload: dict[str, object]) -> dict[str, object]:
        """Explicit UI continuation permits a new exchange budget."""
        connection = self.connection_for(payload)
        await connection.continue_exchange()
        return {"account_id": connection.account_id}
