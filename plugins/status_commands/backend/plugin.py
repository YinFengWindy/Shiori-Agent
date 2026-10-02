"""Scoped assembly for the status command plugin."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .kvcache import KVCacheCommandModule
from .memory_status import MemoryStatusCommandModule

if TYPE_CHECKING:
    from shiori_sdk.extensions import CommandPluginContext as PluginRuntimeContext


async def setup(ctx: PluginRuntimeContext) -> None:
    """Register diagnostic commands independently of optional observe telemetry."""
    ctx.lifecycle.contribute(
        "before_turn",
        [MemoryStatusCommandModule(), KVCacheCommandModule(ctx.dependencies)],
    )
    ctx.bot_commands.add("memorystatus", "查看记忆整理状态")
    ctx.bot_commands.add("kvcache", "查看 KVCache 状态")
