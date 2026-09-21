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
        self._active: set[asyncio.Task[str | ToolResult]] = set()
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
            session = self._sessions.pop(role_id, None)
            if session is not None:
                await session.close(graceful=True)
            return "浏览器会话已关闭，站点状态已保留。"
        if role_id not in self._sessions:
            self._sessions[role_id] = BrowserSession(
                self._root,
                role_id,
                self._config,
                self._runtime or BrowserRuntime.resolve(),
            )
        session = self._sessions[role_id]
        task = asyncio.create_task(session.call(name, arguments))
        self._active.add(task)
        try:
            return await task
        except BaseException:
            if session.closed and self._sessions.get(role_id) is session:
                self._sessions.pop(role_id)
            raise
        finally:
            self._active.discard(task)

    async def close(self) -> None:
        """Closes admission, cancels outstanding actions, then releases all role sessions."""
        self._closed = True
        pending = tuple(self._active)
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        sessions = tuple(self._sessions.values())
        self._sessions.clear()
        results = await asyncio.gather(
            *(session.close(graceful=True) for session in sessions),
            return_exceptions=True,
        )
        errors = [result for result in results if isinstance(result, Exception)]
        if errors:
            raise ExceptionGroup("Browser Use 会话清理失败", errors)
