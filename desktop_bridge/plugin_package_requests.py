from __future__ import annotations

from typing import Any

from agent.plugin_packages import PluginPackageService
from agent.plugin_runtime import PluginRuntimeManager


class DesktopPluginPackageRequestHandler:
    """Handles package catalog and installation RPCs for the desktop client."""

    def __init__(
        self,
        service: PluginPackageService,
        runtime: PluginRuntimeManager | None = None,
    ) -> None:
        self._service = service
        self._runtime = runtime

    async def handle(
        self,
        method: str,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Dispatches one host-owned plugin package request."""

        if not method.startswith("plugins."):
            return None
        if method == "plugins.catalog":
            return {"plugins": await self._service.catalog()}
        if method == "plugins.installed":
            return {"plugins": self._service.installed()}
        if method == "plugins.install":
            repository = str(payload.get("repository") or "").strip()
            if not repository:
                raise ValueError("repository is required")
            installed = await self._service.install(repository)
            if self._runtime is not None and installed.enabled:
                try:
                    await self._runtime.start(installed.plugin_id)
                except Exception:
                    self._service.set_enabled(installed.plugin_id, False)
                    raise
            return {"plugin": installed.to_dict()}
        if method == "plugins.uninstall":
            plugin_id = str(payload.get("plugin_id") or "").strip()
            if not plugin_id:
                raise ValueError("plugin_id is required")
            purge_data = payload.get("purge_data", False)
            if not isinstance(purge_data, bool):
                raise ValueError("purge_data must be a boolean")
            if self._runtime is not None:
                await self._runtime.stop(plugin_id)
            return {
                "removed": self._service.uninstall(
                    plugin_id,
                    purge_data=purge_data,
                )
            }
        if method == "plugins.enable":
            plugin_id = _required_plugin_id(payload)
            plugin = self._service.set_enabled(plugin_id, True)
            if self._runtime is not None:
                try:
                    await self._runtime.start(plugin_id)
                except Exception:
                    self._service.set_enabled(plugin_id, False)
                    raise
            return {"plugin": plugin}
        if method == "plugins.disable":
            plugin_id = _required_plugin_id(payload)
            if self._runtime is not None:
                await self._runtime.stop(plugin_id)
            return {"plugin": self._service.set_enabled(plugin_id, False)}
        if method == "plugins.rpc":
            if self._runtime is None:
                raise RuntimeError("plugin runtime is unavailable")
            plugin_id = _required_plugin_id(payload)
            rpc_method = str(payload.get("method") or "").strip()
            if not rpc_method:
                raise ValueError("method is required")
            rpc_payload = payload.get("payload", {})
            if not isinstance(rpc_payload, dict):
                raise ValueError("payload must be an object")
            return {
                "result": await self._runtime.call_rpc(
                    plugin_id,
                    rpc_method,
                    rpc_payload,
                )
            }
        raise ValueError(f"unknown plugin package method: {method}")


def _required_plugin_id(payload: dict[str, Any]) -> str:
    plugin_id = str(payload.get("plugin_id") or "").strip()
    if not plugin_id:
        raise ValueError("plugin_id is required")
    return plugin_id
