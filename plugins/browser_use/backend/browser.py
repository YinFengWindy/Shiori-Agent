"""Plugin-scoped role session ownership and cancellation."""

import asyncio
from pathlib import Path
from typing import Any

from agent.tools.base import ToolResult

from .config import BrowserUseConfig
from .runtime import BrowserRuntime
from .session import BrowserSession


class BrowserSessions:
    """Keeps separate role profiles and reaps all calls when a plugin generation ends."""

    def __init__(
        self,
        root: Path,
        config: BrowserUseConfig,
        *,
        runtime: BrowserRuntime | None = None,
    ) -> None:
        self._root, self._config, self._runtime = root, config, runtime
        self._sessions: dict[str, BrowserSession] = {}
        self._active: dict[asyncio.Task[str | ToolResult], BrowserSession] = {}
        self._closing: dict[str, asyncio.Task[str]] = {}
        self._closed = False

    async def call(
        self, role_id: str, name: str, arguments: dict[str, Any]
    ) -> str | ToolResult:
        """Uses the host role identity; cancelled sessions cannot perform queued work."""
        if self._closed:
            raise RuntimeError("Browser Use 插件已停用")
        if not role_id.strip():
            raise ValueError("当前会话缺少角色身份，无法操作浏览器")
        if name == "agent_browser_close":
            session = self._sessions.get(role_id)
            if session is None:
                return "浏览器会话已关闭，站点状态已保留。"
            return await self._wait_close(role_id, self._begin_close(role_id, session))
        if role_id in self._closing:
            raise RuntimeError("Browser Use 会话正在关闭，请稍后重试")
        if role_id not in self._sessions:
            self._sessions[role_id] = BrowserSession(
                self._root,
                role_id,
                self._config,
                self._runtime or BrowserRuntime.resolve(),
            )
        session = self._sessions[role_id]
        task = asyncio.create_task(session.call(name, arguments))
        self._active[task] = session
        try:
            return await task
        except BaseException:
            if session.closed and self._sessions.get(role_id) is session:
                await self._wait_close(role_id, self._begin_close(role_id, session))
            raise
        finally:
            self._active.pop(task, None)

    def _begin_close(self, role_id: str, session: BrowserSession) -> asyncio.Task[str]:
        if role_id not in self._closing:
            # Keep the generation in _sessions until cleanup completes. A new
            # caller must not acquire its profile while startup is unwinding.
            session.stop()
            self._closing[role_id] = asyncio.create_task(
                self._close_session(role_id, session)
            )
        return self._closing[role_id]

    async def _close_session(self, role_id: str, session: BrowserSession) -> str:
        pending = tuple(
            task for task, owner in self._active.items() if owner is session
        )
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        await session.close(graceful=True)
        if self._sessions.get(role_id) is session:
            self._sessions.pop(role_id)
        self._closing.pop(role_id, None)
        return "浏览器会话已关闭，站点状态已保留。"

    async def _wait_close(self, role_id: str, task: asyncio.Task[str]) -> str:
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            # An abandoned waiter does not abandon the close result. In
            # particular, unload must still observe a later cleanup failure.
            raise
        except BaseException:
            if self._closing.get(role_id) is task:
                self._closing.pop(role_id)
            raise

    async def close(self) -> None:
        """Closes admission, cancels outstanding actions, then releases all role sessions."""
        self._closed = True
        closing = tuple(
            (role_id, self._begin_close(role_id, session))
            for role_id, session in self._sessions.items()
        )
        # The callers of close tools may already have been cancelled. These
        # shielded, plugin-owned tasks still finish before unload returns.
        results = await asyncio.gather(
            *(self._wait_close(role_id, task) for role_id, task in closing),
            return_exceptions=True,
        )
        errors = [result for result in results if isinstance(result, Exception)]
        if errors:
            raise ExceptionGroup("Browser Use 会话清理失败", errors)
