from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from agent.config_models import Config
from agent.provider import LLMProvider
from core.memory.markdown import build_markdown_memory_runtime
from core.memory.runtime import MemoryRuntime

if TYPE_CHECKING:
    from bus.event_bus import EventBus


def build_memory_runtime(
    config: Config,
    workspace: Path,
    provider: LLMProvider,
    light_provider: LLMProvider | None,
    event_publisher: "EventBus | None" = None,
) -> MemoryRuntime:
    """Markdown memory plus a getter later bound to this generation's socket.

    The semantic engine is not built here. ``default_memory`` (or another
    provider) constructs it during plugin setup and provides ``MEMORY_ENGINE``.
    """
    markdown = build_markdown_memory_runtime(
        workspace=workspace,
        provider=provider,
        model=config.model,
        keep_count=_memory_keep_count(config.memory_window),
        event_bus=event_publisher,
        recent_context_provider=light_provider or provider,
        recent_context_model=config.light_model or config.model,
    )
    return MemoryRuntime(markdown=markdown)


def _memory_keep_count(window: int) -> int:
    aligned_window = max(4, ((max(1, window) + 3) // 4) * 4)
    return aligned_window // 2
