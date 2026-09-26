"""Host account registration and live QQBot application reports."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agent.plugin_host.runtime_context import PluginRuntimeContext

    from .accounts import QQBotAccountStore

_CAPABILITIES = frozenset({"private", "c2c", "known_targets", "send"})


class QQBotAccountIdentity:
    """Keep bot identity and connection reports separate from gateway routing."""

    def __init__(self, ctx: PluginRuntimeContext, store: QQBotAccountStore) -> None:
        self._ctx = ctx
        self._store = store
        self._account_ids: dict[str, str] = {}
        self._pending_identity: dict[str, tuple[str, str]] = {}
        self._handoffs: set[str] = set()
        for row in store.list():
            self.register(row)

    def register(self, row: dict[str, Any], name: str = "") -> str:
        """Associate an application ID with one host account record."""
        app_id = row["app_id"]
        snapshot = self._ctx.accounts.register(
            platform="qqbot",
            platform_account_id=app_id,
            config_ref=f"app:{app_id}",
            display_name=name or row.get("bot_name") or None,
        )
        self._account_ids[app_id] = snapshot.record.id
        return snapshot.record.id

    def account_id(self, app_id: str) -> str:
        """Return the registered ID, or empty while a new gateway is staged."""
        return self._account_ids.get(app_id, "")

    def app_for_account(self, payload: dict[str, Any]) -> str:
        """Resolve a plugin RPC's account ID to its application ID."""
        account_id = str(payload.get("account_id") or "")
        return next(
            app_id
            for app_id, registered in self._account_ids.items()
            if registered == account_id
        )

    def begin_handoff(self, app_id: str) -> None:
        """Hold Gateway identity changes until replacement credentials commit."""
        self._handoffs.add(app_id)

    def pending_identity(self, app_id: str) -> tuple[str, str]:
        """Read READY identity without publishing the staged credentials yet."""
        return self._pending_identity.get(app_id, ("", ""))

    def end_handoff(self, app_id: str) -> tuple[str, str]:
        """Finish a handoff and return any READY bot identity it observed."""
        self._handoffs.discard(app_id)
        return self._pending_identity.pop(app_id, ("", ""))

    def report(
        self, app_id: str, state: str, error: str, name: str, bot_id: str = ""
    ) -> None:
        """Publish connection state and verified bot display identity."""
        if app_id in self._handoffs or app_id not in self._account_ids:
            if name or bot_id:
                self._pending_identity[app_id] = (name, bot_id)
            if app_id in self._account_ids:
                self._report_connection(app_id, state, error)
            return
        if name or bot_id:
            row = self._store.get(app_id)
            self._store.save(
                {
                    **row,
                    "bot_name": name or row.get("bot_name", ""),
                    "bot_id": bot_id or row.get("bot_id", ""),
                }
            )
            self.register(row, name)
        self._report_connection(app_id, state, error)

    def _report_connection(self, app_id: str, state: str, error: str) -> None:
        self._ctx.accounts.report(
            self._account_ids[app_id],
            connection=state,
            capabilities=_CAPABILITIES if state == "online" else frozenset(),
            error=error,
        )

    def unregister_all(self) -> None:
        """Discard runtime presence while retaining saved account records."""
        for account_id in self._account_ids.values():
            self._ctx.accounts.unregister(account_id)
