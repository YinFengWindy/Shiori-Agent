"""Independent plugin discovery and package installation contracts."""

from agent.plugin_packages.catalog import GitHubPluginCatalog
from agent.plugin_packages.contracts import (
    HOST_PLUGIN_API_VERSION,
    PLUGIN_REPOSITORY_MANIFEST_PATH,
    PluginCatalogEntry,
    PluginManifest,
    PluginManifestError,
    PluginRelease,
)
from agent.plugin_packages.installer import InstalledPlugin, PluginPackageInstaller
from agent.plugin_packages.service import PluginPackageService

__all__ = [
    "GitHubPluginCatalog",
    "HOST_PLUGIN_API_VERSION",
    "InstalledPlugin",
    "PLUGIN_REPOSITORY_MANIFEST_PATH",
    "PluginCatalogEntry",
    "PluginManifest",
    "PluginManifestError",
    "PluginPackageInstaller",
    "PluginPackageService",
    "PluginRelease",
]
