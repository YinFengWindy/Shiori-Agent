"""Native boundary fakes that never launch a process or connect to MCP."""

import asyncio
from contextvars import ContextVar
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import BinaryIO
from shiori_sdk.mcp import McpToolInfo
from shiori_sdk.tools import ToolResult
from shiori_sdk.processes import ProcessOwner


class FakeMcpSession:
    """Patchable explicit connection double for plugin cancellation tests."""

    def __init__(
        self,
        name: str,
        command: list[str],
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        *,
        own_process_tree: bool = False,
        inherit_env: bool = True,
    ):
        self.name, self.command, self.env, self.cwd = name, command, env, cwd
        self.own_process_tree, self.inherit_env = own_process_tree, inherit_env

    async def connect(self) -> list[McpToolInfo]:
        """A successful fake session has no discovered tools by default."""
        return []

    async def call(
        self,
        tool_name: str,
        arguments: dict[str, object],
        *,
        timeout: float | None = None,
    ) -> str | ToolResult:
        """Require explicit test configuration for every native action."""
        raise AssertionError(f"Unconfigured MCP call: {tool_name}")

    async def disconnect(self) -> None:
        """The fake owns no operating-system resources."""


class FakeProcesses:
    """Create only fake MCP sessions; native process tests belong to the host."""

    def mcp(
        self,
        name: str,
        command: list[str],
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        *,
        own_process_tree: bool = False,
        inherit_env: bool = True,
    ):
        """Construct a controlled MCP endpoint without opening it."""
        return FakeMcpSession(
            name,
            command,
            env,
            cwd,
            own_process_tree=own_process_tree,
            inherit_env=inherit_env,
        )

    async def spawn(
        self,
        *command: str,
        env: dict[str, str],
        cwd: str,
        stdin: int,
        stdout: BinaryIO,
        stderr: BinaryIO,
    ) -> tuple[asyncio.subprocess.Process, ProcessOwner | None]:
        """Reject accidental native process starts in independent plugin tests."""
        raise AssertionError(f"Native spawn requires an explicit fixture: {command}")


class FakeToolTurn:
    """Explicit turn identity and awaited cleanup for plugin-owned resource tests."""

    def __init__(self):
        self.closed = False
        self.task = asyncio.current_task()
        self.finalizers: dict[object, Callable[[], Awaitable[None]]] = {}
        self.cleanup: asyncio.Task[None] | None = None

    def own(self, key: object, release: Callable[[], Awaitable[None]]) -> None:
        """Retain one finalizer for this controlled identity."""
        if self.closed:
            raise RuntimeError("工具回合已结束")
        self.finalizers.setdefault(key, release)

    async def close(self) -> None:
        """Join all cleanup even when the waiting test task is cancelled."""
        self.closed = True
        if self.cleanup is None:
            self.cleanup = asyncio.create_task(self._close())
        await asyncio.shield(self.cleanup)

    async def _close(self) -> None:
        results = await asyncio.gather(
            *(release() for release in reversed(tuple(self.finalizers.values()))),
            return_exceptions=True,
        )
        errors = [item for item in results if isinstance(item, BaseException)]
        if errors:
            raise BaseExceptionGroup("工具回合资源释放失败", errors)


_turn: ContextVar[FakeToolTurn | None] = ContextVar("sdk_fake_turn", default=None)


def current_tool_turn() -> FakeToolTurn:
    """Read the test-controlled turn, never a host context variable."""
    turn = _turn.get()
    if turn is None or turn.closed:
        raise RuntimeError("Computer Use 需要有效的宿主工具回合")
    return turn


def tool_turn[**P, R](function: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
    """Run a test scenario inside an explicit fake turn and finalize its resources."""

    @wraps(function)
    async def run(*args: P.args, **kwargs: P.kwargs) -> R:
        existing = _turn.get()
        if existing is not None and existing.task is asyncio.current_task():
            if existing.closed:
                raise RuntimeError("工具回合已结束")
            return await function(*args, **kwargs)
        scope = FakeToolTurn()
        token = _turn.set(scope)
        try:
            return await function(*args, **kwargs)
        finally:
            try:
                await scope.close()
            finally:
                _turn.reset(token)

    return run
