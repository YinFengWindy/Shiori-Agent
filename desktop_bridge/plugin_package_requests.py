from __future__ import annotations

from typing import Any

from agent.plugin_packages import PluginPackageService


class DesktopPluginPackageRequestHandler:
    """Handles package catalog and installation RPCs for the desktop client."""

    def __init__(self, service: PluginPackageService) -> None:
        self._service = service

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
            return {"plugin": installed.to_dict()}
        if method == "plugins.uninstall":
            plugin_id = str(payload.get("plugin_id") or "").strip()
            if not plugin_id:
                raise ValueError("plugin_id is required")
            purge_data = payload.get("purge_data", False)
            if not isinstance(purge_data, bool):
                raise ValueError("purge_data must be a boolean")
            return {
                "removed": self._service.uninstall(
                    plugin_id,
                    purge_data=purge_data,
                )
            }
        raise ValueError(f"unknown plugin package method: {method}")
