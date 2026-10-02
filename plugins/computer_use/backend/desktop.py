"""Host-turn desktop ownership, cancellation and plugin-generation teardown."""

import asyncio
from pathlib import Path
from typing import Any
from weakref import WeakSet

from shiori_sdk.mcp import McpToolError
from shiori_sdk.tools import ToolResult
from shiori_sdk.processes import ToolTurn, Processes
from collections.abc import Callable

from .config import ComputerUseConfig
from .session import DesktopSession
from .windows import TargetError


class ComputerDesktop:
    """Keeps a role's lease across observations, actions and model waits in one turn."""

    def __init__(
        self,
        root: Path,
        config: ComputerUseConfig,
        *,
        processes: Processes,
        resources: Path,
        current_turn: Callable[[], ToolTurn],
    ) -> None:
        self._processes, self._resources, self._current_turn = (
            processes,
            resources,
            current_turn,
        )
        self._root, self._config = root, config
        self._owner: tuple[ToolTurn, str] | None = None
        self._session: DesktopSession | None = None
        self._active: set[asyncio.Task[str | ToolResult]] = set()
        self._closing: asyncio.Task[None] | None = None
        self._revoked: WeakSet[ToolTurn] = WeakSet()
        self._closed = False

    async def call(
        self, role_id: str, name: str, arguments: dict[str, Any]
    ) -> str | ToolResult:
        """Rejects competing roles/turns immediately rather than queueing stale intent."""
        if self._closed:
            raise RuntimeError("Computer Use 插件已停用")
        scope = self._current_turn()
        if not role_id.strip():
            raise ValueError("Computer Use 缺少宿主角色身份")
        if scope in self._revoked:
            raise RuntimeError("Computer Use 本回合已停止，请开启新回合")
        if self._closing is not None or (
            self._owner is not None and self._owner != (scope, role_id)
        ):
            raise RuntimeError("Computer Use 桌面正由其他任务或运行代占用，请稍后重试")
        if name == "release":
            await self._release(scope)
            return "Computer Use 桌面控制已释放。"
        if self._session is None:
            self._owner = (scope, role_id)
            self._session = DesktopSession(
                self._root, self._config, self._processes, self._resources
            )
            scope.own(self, lambda: self._release(scope))
        session = self._session
        task = asyncio.create_task(session.call(name, arguments))
        self._active.add(task)
        try:
            return await task
        except (McpToolError, TargetError):
            # A completed stale-element/action refusal still permits observation.
            # Startup errors have no connected/usable generation and are closed.
            if not session.ready:
                await self._release(scope)
            raise
        except BaseException:
            await self._release(scope)
            raise
        finally:
            self._active.discard(task)

    async def _release(self, scope: ToolTurn) -> None:
        self._revoked.add(scope)
        if self._owner is None and self._closing is None:
            return
        if self._owner is not None and self._owner[0] is not scope:
            return
        if self._closing is None:
            assert self._session is not None
            self._session.stop()
            self._closing = asyncio.create_task(self._dispose())
        # Cleanup survives a cancelled waiter and remains tracked for unload.
        await asyncio.shield(self._closing)
        self._closing = None

    async def _dispose(self) -> None:
        tasks = tuple(self._active)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        assert self._session is not None
        await self._session.close()
        self._session = None
        self._owner = None

    async def close(self) -> None:
        """Stops admission before joining active/queued work and retained cleanup."""
        self._closed = True
        if self._owner is not None:
            await self._release(self._owner[0])
        elif self._closing is not None:
            await asyncio.shield(self._closing)
            self._closing = None
