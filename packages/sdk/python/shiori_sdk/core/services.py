"""Public keys for the services plugins used to take as capabilities.

P4-3 publishes one key per former capability. The name is the capability
name, except ``session_store``: ``sessions`` is already the rollback socket
(``shiori_sdk.core.sessions``). A plugin lists the name in ``inject`` and
takes the object with ``ctx.require``. The host provides these keys before
any plugin starts.

Plugins take them with ``ctx.require`` / ``ctx.get``. ``EVENTS`` is the
domain event bus, not kernel ``on`` / ``watch``.
``BACKGROUND`` is named tasks, not kernel ``spawn``. ``WORKSPACE`` is the
host workspace directory, not kernel ``data_dir``. ``MEMORY`` is the memory
plugin surface, not ``MEMORY_ENGINE``.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from shiori_sdk.accounts.capability import AccountsCapability
from shiori_sdk.background_results import BackgroundResults
from shiori_sdk.channels.avatars import AvatarsCapability
from shiori_sdk.channels.context import ChannelsCapability
from shiori_sdk.extensions import (
    BackgroundTasks,
    ConfigValues,
    Dependencies,
    PrivateStorage,
)
from shiori_sdk.external_turns import ExternalTurns
from shiori_sdk.http import HttpClient
from shiori_sdk.kernel import Key
from shiori_sdk.memory.context import MemoryCapability
from shiori_sdk.models import ChatProvider, RoleModels
from shiori_sdk.plugin_services import RuntimeLifecycle
from shiori_sdk.process_resources import PluginProcessResources
from shiori_sdk.processes import Processes, Resources, ToolTurn
from shiori_sdk.roles import Roles
from shiori_sdk.rpc import RpcCapability
from shiori_sdk.runtime import EventsCapability
from shiori_sdk.services import PluginServices
from shiori_sdk.sessions import PluginSessions
from shiori_sdk.storage import KeyValueStore
from shiori_sdk.tools import ToolsCapability

TOOLS: Key[ToolsCapability] = Key("tools")
"""Register tools into the generation's tool registry."""

TOOL_TURN: Key[Callable[[], ToolTurn]] = Key("tool_turn")
"""The tool turn running in the current task, if one is."""

CHANNELS: Key[ChannelsCapability] = Key("channels")
"""Contribute declared transports to the host lifecycle."""

ACCOUNTS: Key[AccountsCapability] = Key("accounts")
"""Register communication accounts and report their lifecycle."""

AVATARS: Key[AvatarsCapability] = Key("avatars")
"""The shared avatar cache."""

SESSION_STORE: Key[PluginSessions] = Key("session_store")
"""Session metadata and original media.

Not ``SESSIONS`` (name ``sessions``), which rolls back the latest passive
turn. A plugin that read the ``sessions`` capability injects ``session_store``.
"""

ROLES: Key[Roles] = Key("roles")
"""The canonical role store."""

MODELS: Key[RoleModels] = Key("models")
"""Per-role chat models."""

LIGHT_PROVIDER: Key[ChatProvider] = Key("light_provider")
"""The light chat provider. Distinct from ``MAIN_PROVIDER``."""

LIGHT_MODEL: Key[str] = Key("light_model")
"""The model name paired with ``LIGHT_PROVIDER``."""

MEMORY: Key[MemoryCapability] = Key("memory")
"""The memory plugin's host surface. The engine is ``MEMORY_ENGINE``."""

PROCESSES: Key[Processes] = Key("processes")
"""Host-owned native processes."""

RESOURCES: Key[Resources] = Key("resources")
"""Host-distributed resources."""

EXTERNAL_TURNS: Key[ExternalTurns] = Key("external_turns")
"""Submit a turn that did not start in the desktop conversation."""

BACKGROUND_RESULTS: Key[BackgroundResults] = Key("background_results")
"""Where a background task posts its result."""

BACKGROUND: Key[BackgroundTasks] = Key("background")
"""Named tasks owned by the plugin until cleanup. Not kernel ``spawn``."""

EVENTS: Key[EventsCapability] = Key("events")
"""The domain event bus. Not kernel ``on`` / ``watch`` / ``emit``."""

RPC: Key[RpcCapability] = Key("rpc")
"""Bridge-callable plugin methods."""

WORKSPACE: Key[Path] = Key("workspace")
"""The host workspace directory. Plugin data stays under ``plugin-data``."""

HTTP: Key[HttpClient] = Key("http")
"""The shared external HTTP requester."""

PROCESS_RESOURCES: Key[PluginProcessResources] = Key("process_resources")
"""Process-owned resources that outlive one generation."""

CONFIG: Key[ConfigValues] = Key("config")
"""This plugin's resolved configuration."""

KV: Key[KeyValueStore] = Key("kv")
"""This plugin's JSON records under the workspace."""

DEPENDENCIES: Key[Dependencies] = Key("dependencies")
"""Exports of the plugins named in ``dependencies``."""

RUNTIME: Key[RuntimeLifecycle] = Key("runtime")
"""Drain accepted work before a replacing generation takes over."""

SERVICES: Key[PluginServices] = Key("services")
"""Publish a discoverable service contract."""

STORAGE: Key[PrivateStorage] = Key("storage")
"""Host-owned migration of this plugin's files."""
