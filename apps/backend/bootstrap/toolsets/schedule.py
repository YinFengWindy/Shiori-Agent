"""The ``schedule`` toolset name remains resolvable for old configs.

Schedule tools now come from the ``schedule`` plugin. Listing ``schedule``
here registers nothing.
"""

from __future__ import annotations

import logging

from agent.tools.registry import ToolRegistry
from bootstrap.toolsets.protocol import ToolsetDeps, ToolsetRegistrationResult

logger = logging.getLogger(__name__)


class SchedulerToolsetProvider:
    """Accepts a legacy ``schedule`` toolset without registering host tools."""

    def register(
        self, registry: ToolRegistry, deps: ToolsetDeps
    ) -> ToolsetRegistrationResult:
        logger.info("toolset schedule 已由插件 schedule 提供，核心不再注册计划任务工具")
        return ToolsetRegistrationResult(source_name="schedule")
