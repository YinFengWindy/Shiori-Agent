"""``accounts.delete``: plugin cleanup, optional config write, then host removal.

Lives beside the plugin-config channel rather than in a generation's account
handler because a plugin whose credential sits in ``[plugins.<id>]`` needs the
settings transaction to rewrite that table, which replaces the generation that
would otherwise be serving the request.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import uuid4

from core.roles import RoleStore
from desktop_bridge.runtime.apply import RuntimeApplyError
from desktop_bridge.runtime.plugin_config import RuntimePluginConfig


class RuntimeAccountDeletion:
    """Deletes one role-owned account through its owning plugin's delete hook."""

    def __init__(self, roles: RoleStore, plugin_config: RuntimePluginConfig) -> None:
        self._roles = roles
        self._plugin_config = plugin_config

    async def delete(
        self,
        payload: dict[str, Any],
        *,
        prepare_service: Callable,
        publish_service: Callable,
    ) -> dict[str, Any]:
        """Returns the applied config result when the plugin table was rewritten."""
        account_id = str(payload.get("account_id") or "").strip()
        role_id = str(payload.get("role_id") or "").strip()
        if not account_id or not role_id:
            raise RuntimeApplyError(
                "runtime_invalid_request", "account_id 和 role_id 不能为空"
            )
        applied: dict[str, Any] | None = None

        async def write_plugin_config(plugin_id: str, values: dict[str, Any]) -> None:
            nonlocal applied
            applied = await self._plugin_config.replace_from_plugin(
                plugin_id,
                values,
                operation_id=f"account-delete:{account_id}:{uuid4().hex}",
                prepare_service=prepare_service,
                publish_service=publish_service,
            )

        await self._roles.accounts.delete(
            account_id, role_id=role_id, write_plugin_config=write_plugin_config
        )
        return {"account_id": account_id, "config": applied}
