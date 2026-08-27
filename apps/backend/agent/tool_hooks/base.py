from __future__ import annotations

from abc import ABC, abstractmethod

from agent.tool_hooks.types import HookContext, HookEvent, HookOutcome


class ToolHook(ABC):
    name: str
    event: HookEvent

    @abstractmethod
    def matches(self, ctx: HookContext) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def run(self, ctx: HookContext) -> HookOutcome:
        raise NotImplementedError
