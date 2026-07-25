from __future__ import annotations

from agent.plugins import Plugin
from core.roles.store import RoleStore
from plugins.desktop_pet.tool import DesktopPetActionTool


class DesktopPetPlugin(Plugin):
    """Registers the role-facing desktop-pet action tool."""

    name = "desktop_pet"

    async def initialize(self) -> None:
        workspace = self.context.workspace
        if workspace is None:
            raise RuntimeError("桌宠插件需要 workspace")
        self._tool = DesktopPetActionTool(
            role_store=RoleStore(workspace),
            event_bus=self.context.event_bus,
            tool_registry=self.context.tool_registry,
        )
        self.context.tool_registry.register(
            self._tool,
            risk="external-side-effect",
            always_on=True,
            search_hint="桌宠 移动 位置 动作 挥手 跳跃",
            source_type="plugin",
            source_name=self.name,
        )

    async def terminate(self) -> None:
        tool = getattr(self, "_tool", None)
        if tool is not None:
            self.context.tool_registry.unregister(tool.name)
