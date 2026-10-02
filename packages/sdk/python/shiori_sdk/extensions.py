"""Small setup surfaces for hook, command, and observation plugins."""

import asyncio
from collections.abc import Coroutine
from pathlib import Path
from typing import Protocol
from .runtime import PluginRuntimeContext
from .tool_hooks import ToolHooksCapability
from .sessions import SessionUndo
from .memory.engine import MemoryEngine
from .diagnostics import Diagnostics


class ConfigValues(Protocol):
    """Resolved plugin-owned configuration snapshot."""

    def as_dict(self) -> dict[str, object]: ...
    def resolve_reference(self, value: str) -> str:
        """Resolve a stored credential reference at use time without persisting its value."""
        ...


class BotCommands(Protocol):
    """Contribute command-menu entries for this generation."""

    def add(self, command: str, description: str) -> None: ...


class Dependencies(Protocol):
    """Resolve the current export only for explicitly declared dependencies."""

    def require(self, plugin_id: str) -> object: ...
    def get_optional(self, plugin_id: str) -> object | None: ...


class BackgroundTasks(Protocol):
    """Own cancellable coroutines until plugin cleanup finishes."""

    def spawn[T](
        self, coro: Coroutine[object, object, T], *, name: str
    ) -> asyncio.Task[T]: ...

    def spawn_runtime[T](
        self, coro: Coroutine[object, object, T], *, name: str
    ) -> asyncio.Task[T]:
        """Retain the calling runtime lease until task completion and cleanup."""
        ...


class PrivateStorage(Protocol):
    """Delegate migration to the host owner and use its returned destination.

    Files for one plugin share the owner's selected directory. The canonical
    layout is given by storage.plugin_data_dir; consumers must honor the actual
    migration result when the owner selects a different storage root.
    """

    def migrate_data(
        self, workspace: Path, plugin_id: str, name: str, source: Path
    ) -> Path: ...


class HookPluginContext(PluginRuntimeContext, Protocol):
    """Granted inputs consumed by tool policy plugins."""

    @property
    def workspace(self) -> Path | None: ...
    @property
    def tool_hooks(self) -> ToolHooksCapability: ...
    @property
    def config(self) -> ConfigValues: ...


class CommandPluginContext(PluginRuntimeContext, Protocol):
    """Command registration and bounded undo/dependency services."""

    @property
    def bot_commands(self) -> BotCommands: ...
    @property
    def dependencies(self) -> Dependencies: ...
    @property
    def session_manager(self) -> SessionUndo | None: ...
    @property
    def memory_engine(self) -> MemoryEngine | None: ...


class ObservePluginContext(PluginRuntimeContext, Protocol):
    """Explicit storage, diagnostics and task services for event observers."""

    @property
    def workspace(self) -> Path | None: ...
    @property
    def diagnostics(self) -> Diagnostics: ...
    @property
    def storage(self) -> PrivateStorage: ...
    @property
    def background(self) -> BackgroundTasks: ...
