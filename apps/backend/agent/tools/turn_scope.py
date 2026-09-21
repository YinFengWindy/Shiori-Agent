"""Lifetime for resources held across the tool calls of one reasoning turn."""

import asyncio
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from functools import wraps
from typing import ParamSpec, TypeVar

_P = ParamSpec("_P")
_R = TypeVar("_R")
_current: ContextVar["ToolTurnScope | None"] = ContextVar(
    "tool_turn_scope", default=None
)


class ToolTurnScope:
    """Host identity and awaited finalizers, including cancelled/failed turns."""

    def __init__(self) -> None:
        self.closed = False
        self.task = asyncio.current_task()
        self._finalizers: dict[object, Callable[[], Awaitable[None]]] = {}
        self._cleanup: asyncio.Task[None] | None = None

    def own(self, key: object, release: Callable[[], Awaitable[None]]) -> None:
        """Registers one owner cleanup; child tasks inherit the same turn identity."""
        if self.closed:
            raise RuntimeError("工具回合已结束")
        self._finalizers.setdefault(key, release)

    async def close(self) -> None:
        """Closes admission before awaiting every registered resource release."""
        self.closed = True
        if self._cleanup is None:
            self._cleanup = asyncio.create_task(self._release_all())
        await asyncio.shield(self._cleanup)

    async def _release_all(self) -> None:
        results = await asyncio.gather(
            *(release() for release in reversed(tuple(self._finalizers.values()))),
            return_exceptions=True,
        )
        errors = [result for result in results if isinstance(result, BaseException)]
        if errors:
            raise BaseExceptionGroup("工具回合资源释放失败", errors)


def current_tool_turn() -> ToolTurnScope:
    """Returns a live host turn; model parameters cannot forge this identity."""
    scope = _current.get()
    if scope is None or scope.closed:
        raise RuntimeError("Computer Use 需要有效的宿主工具回合")
    return scope


def tool_turn(
    function: Callable[_P, Awaitable[_R]],
) -> Callable[_P, Awaitable[_R]]:
    """Wraps a reasoning entrypoint with deterministic tool-resource cleanup."""

    @wraps(function)
    async def run(*args: _P.args, **kwargs: _P.kwargs) -> _R:
        existing = _current.get()
        if existing is not None and existing.task is asyncio.current_task():
            if existing.closed:
                raise RuntimeError("工具回合已结束")
            return await function(*args, **kwargs)
        scope = ToolTurnScope()
        token = _current.set(scope)
        try:
            return await function(*args, **kwargs)
        finally:
            try:
                await scope.close()
            finally:
                _current.reset(token)

    return run
