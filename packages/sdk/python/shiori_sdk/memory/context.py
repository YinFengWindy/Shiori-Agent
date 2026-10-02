"""Granted setup operations for memory-owned Dashboard RPCs."""

from pathlib import Path
from typing import Protocol

from shiori_sdk.rpc import RpcCapability
from shiori_sdk.runtime import PluginRuntimeContext

from .build import MemoryRoles, MemoryStorage
from .engine import MemoryEngine


class MemoryCapability(Protocol):
    """Host state needed by memory plugins, without private role/config services."""

    @property
    def workspace(self) -> Path: ...
    @property
    def engine(self) -> MemoryEngine | None: ...
    @property
    def roles(self) -> MemoryRoles: ...
    @property
    def storage(self) -> MemoryStorage: ...
    async def read_documents(self, payload: dict[str, object]) -> dict[str, object]: ...


class MemoryPluginContext(PluginRuntimeContext, Protocol):
    """Setup context for plugins declaring memory and RPC capabilities."""

    @property
    def memory(self) -> MemoryCapability: ...
    @property
    def rpc(self) -> RpcCapability: ...
