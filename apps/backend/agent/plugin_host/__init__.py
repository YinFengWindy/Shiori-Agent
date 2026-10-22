"""插件内核公共入口：内核、manifest、运行时上下文与 capability 契约。"""

from agent.plugin_host.capabilities import PluginContributions
from agent.plugin_host.config_schema import (
    ConfigModelError,
    PluginConfigSchemaRegistry,
    resolve_config_model,
)
from agent.plugin_host.handle import PluginHandle, PluginRecord, PluginState
from agent.plugin_host.kernel import PluginGenerationSettings, PluginKernel
from agent.plugin_host.manifest import (
    DEFAULT_ENTRY,
    ChannelDeclaration,
    ManifestError,
    PluginManifest,
    load_manifest,
)
from agent.plugin_host.reload import PluginReloadResult
from agent.plugin_host.rpc import PluginRpcRegistry
from agent.plugin_host.runtime_context import PluginRuntimeContext
from agent.plugin_host.unload import (
    PluginReloadFailed,
    PluginReloadTimeout,
    PluginReloadUnsupported,
    PluginRestartRequired,
)

__all__ = [
    "ChannelDeclaration",
    "ConfigModelError",
    "DEFAULT_ENTRY",
    "ManifestError",
    "PluginConfigSchemaRegistry",
    "PluginContributions",
    "PluginGenerationSettings",
    "PluginHandle",
    "PluginKernel",
    "PluginManifest",
    "PluginRecord",
    "PluginReloadFailed",
    "PluginReloadResult",
    "PluginReloadTimeout",
    "PluginReloadUnsupported",
    "PluginRestartRequired",
    "PluginRpcRegistry",
    "PluginRuntimeContext",
    "PluginState",
    "load_manifest",
    "resolve_config_model",
]
