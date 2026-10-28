"""Granted setup operations for memory-owned Dashboard RPCs."""

from pathlib import Path
from typing import Protocol

from .access import MemoryRoles, MemoryStorage


class MemoryCapability(Protocol):
    """Host state needed by memory plugins, without private role/config services.

    The engine is not here. The plugin that provides ``MEMORY_ENGINE`` keeps
    the instance it built; other plugins ``get`` the socket.
    """

    @property
    def workspace(self) -> Path: ...
    @property
    def roles(self) -> MemoryRoles: ...
    @property
    def storage(self) -> MemoryStorage: ...
    def skill_names(self) -> list[str]: ...
    async def read_documents(self, payload: dict[str, object]) -> dict[str, object]: ...
