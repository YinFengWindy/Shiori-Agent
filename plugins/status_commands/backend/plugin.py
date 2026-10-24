"""Scoped assembly for the status command plugin."""

from __future__ import annotations

from typing import TYPE_CHECKING

from shiori_sdk.core.conversation import COMMANDS, CommandHandler

from .kvcache import KVCacheCommand
from .memory_status import memory_status

if TYPE_CHECKING:
    from shiori_sdk.extensions import CommandPluginContext as PluginRuntimeContext


async def setup(ctx: PluginRuntimeContext) -> None:
    """Register diagnostic commands independently of optional observe telemetry."""
    kvcache = KVCacheCommand(ctx.dependencies)
    registrations: tuple[tuple[str, CommandHandler, str | None], ...] = (
        ("memorystatus", memory_status, "查看记忆整理状态"),
        ("memory_status", memory_status, None),
        ("compact_status", memory_status, None),
        ("kvcache", kvcache, "查看 KVCache 状态"),
        ("cache_status", kvcache, None),
    )
    commands = ctx.require(COMMANDS)
    for name, handler, description in registrations:
        remove = commands.register(name, handler, description=description)
        ctx.effect(f"command:{name}", remove)
