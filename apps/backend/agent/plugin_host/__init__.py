"""插件内核公共入口：内核、manifest、运行时上下文与 capability 契约。"""

from agent.plugin_host.capabilities import PHASE_SLOTS, PluginContributions
from agent.plugin_host.config_schema import (
    ConfigModelError,
    PluginConfigSchemaRegistry,
    resolve_config_model,
)
from agent.plugin_host.effects import EffectScope
from agent.plugin_host.events import ScopedEventBus
from agent.plugin_host.handle import PluginHandle, PluginRecord, PluginState
from agent.plugin_host.kernel import HostServices, PluginKernel
from agent.plugin_host.manifest import (
    DEFAULT_ENTRY,
    ChannelDeclaration,
    KNOWN_CAPABILITIES,
    ManifestError,
    PluginManifest,
    load_manifest,
)
from agent.plugin_host.rpc import PluginRpcRegistry
from agent.plugin_host.runtime_context import (
    CapabilityNotGranted,
    PluginRuntimeContext,
)
from agent.plugin_host.tool_hooks import PluginToolHook
from agent.plugin_host.unload import PluginRestartRequired

__all__ = [
    "CapabilityNotGranted",
    "ChannelDeclaration",
    "ConfigModelError",
    "DEFAULT_ENTRY",
    "EffectScope",
    "HostServices",
    "KNOWN_CAPABILITIES",
    "ManifestError",
    "PHASE_SLOTS",
    "PluginConfigSchemaRegistry",
    "PluginContributions",
    "PluginHandle",
    "PluginKernel",
    "PluginManifest",
    "PluginRecord",
    "PluginRestartRequired",
    "PluginRpcRegistry",
    "PluginRuntimeContext",
    "PluginState",
    "PluginToolHook",
    "ScopedEventBus",
    "load_manifest",
    "resolve_config_model",
]
