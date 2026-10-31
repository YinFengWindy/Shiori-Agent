"""Memory optimizer: periodically merges roles' pending facts and updates SELF.md.

The loop is a process resource: one per process, started by the first setup
and kept until the plugin is disabled or the process exits. Every generation's
setup only attaches its host services and interval to it.
"""

from __future__ import annotations

import logging

from shiori_sdk.core.markdown_memory import MARKDOWN_MEMORY
from shiori_sdk.core.memory_optimizer import MEMORY_OPTIMIZER
from shiori_sdk.core.models import MAIN_MODEL
from shiori_sdk.core.services import CONFIG, MODELS, PROCESS_RESOURCES, ROLES
from shiori_sdk.runtime import PluginRuntimeContext

from .config import MemoryOptimizerConfig
from .service import MemoryOptimizerService, OptimizerBinding

logger = logging.getLogger(__name__)

# Versioned process-resource contract; bump it when the retained object's
# methods change incompatibly, so a reload builds a fresh service.
_RESOURCE_KEY = "memory-optimizer-v1"


async def setup(ctx: PluginRuntimeContext) -> None:
    """Attaches this generation to the process loop and provides its progress."""
    if not ctx.get(MAIN_MODEL):
        # Without a model registration no role has a chat model to optimize
        # with. The resource is not acquired, so a running loop stops once this
        # generation is published.
        logger.info("[memory_optimizer] 没有模型注册，记忆整理不运行")
        return
    config = MemoryOptimizerConfig.model_validate(ctx.require(CONFIG).as_dict())
    resources = ctx.require(PROCESS_RESOURCES)
    service = resources.acquire(_RESOURCE_KEY, MemoryOptimizerService)
    binding = OptimizerBinding(
        roles=ctx.require(ROLES),
        memory=ctx.require(MARKDOWN_MEMORY),
        models=ctx.require(MODELS),
        interval_seconds=config.interval_seconds,
        is_active=lambda: resources.active,
    )
    ctx.effect("memory_optimizer.binding", service.attach(binding))
    # Wakes a loop that waits for a published binding; runs at once when this
    # generation is already published.
    ctx.effect(
        "memory_optimizer.publication", resources.on_published(service.published)
    )
    ctx.provide(MEMORY_OPTIMIZER, service)
