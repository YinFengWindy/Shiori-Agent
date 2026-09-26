"""Shared registration of the role-memory document RPC for memory plugins."""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.roles.memory_document_requests import RoleMemoryDocumentReader
from core.roles.memory_service import RoleMemoryService

if TYPE_CHECKING:
    from agent.plugin_host.runtime_context import PluginRuntimeContext


def register_role_memory_documents(ctx: PluginRuntimeContext) -> None:
    """Register a scoped read-only document request in the current plugin."""
    from desktop_bridge.method_policy import Concurrency

    if ctx.workspace is None or ctx.role_store is None:
        raise RuntimeError(f"{ctx.plugin_id} 记忆文档读取需要 workspace 和 role_store")
    reader = RoleMemoryDocumentReader(ctx.role_store, RoleMemoryService(ctx.workspace))
    ctx.rpc.register(
        "roles.memory.documents", reader.read, concurrency=Concurrency.READ_ONLY
    )
