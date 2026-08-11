from __future__ import annotations

from agent.plugin_packages.catalog import GitHubPluginCatalog
from agent.plugin_packages.installer import InstalledPlugin, PluginPackageInstaller


class PluginPackageService:
    """Coordinates plugin catalog queries and package installation operations."""

    def __init__(
        self,
        catalog: GitHubPluginCatalog,
        installer: PluginPackageInstaller,
    ) -> None:
        self._catalog = catalog
        self._installer = installer

    async def catalog(self) -> list[dict[str, object]]:
        """Returns renderer-safe plugin catalog records."""

        entries = await self._catalog.list_plugins()
        return [
            {
                "repository": entry.repository,
                "repository_url": entry.repository_url,
                "manifest": entry.manifest.to_dict(),
                "installable": entry.installable,
                "unavailable_reason": entry.unavailable_reason,
                "release_tag": entry.release.tag if entry.release else None,
            }
            for entry in entries
        ]

    def installed(self) -> list[dict[str, object]]:
        """Returns renderer-safe installed plugin records."""

        return [item.to_dict() for item in self._installer.list_installed()]

    async def install(self, repository: str) -> InstalledPlugin:
        """Resolves and installs the latest compatible release from one repository."""

        entry = await self._catalog.get_plugin(repository)
        return await self._installer.install(entry)

    def uninstall(self, plugin_id: str, *, purge_data: bool = False) -> bool:
        """Uninstalls one plugin package and optionally clears its user data."""

        return self._installer.uninstall(plugin_id, purge_data=purge_data)
