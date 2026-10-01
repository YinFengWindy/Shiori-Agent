"""Tracks resources allocated before a complete CoreRuntime owns their lifetime."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from contextlib import AsyncExitStack
from contextvars import ContextVar
from typing import TYPE_CHECKING, TypeVar

from shiori_sdk.memory.build import BuildResource

if TYPE_CHECKING:
    from bootstrap.tools import CoreRuntime

T = TypeVar("T")
_scope: ContextVar[tuple[AsyncExitStack, set[int]] | None] = ContextVar(
    "runtime_construction", default=None
)


def track_build_resource(resource: T, cleanup: Callable[[], object]) -> T:
    """Registers a newly owned resource for cleanup if construction later fails."""
    scope = _scope.get()
    if scope is None or id(resource) in scope[1]:
        return resource
    stack, tracked = scope
    tracked.add(id(resource))

    async def close():
        result = cleanup()
        if inspect.isawaitable(result):
            await result

    stack.push_async_callback(close)
    return resource


def track_build_closeables(resources: list[object]) -> None:
    """Accepts the existing memory plugin closeable contract during construction."""
    for resource in resources:
        cleanup = getattr(resource, "aclose", None) or getattr(resource, "close", None)
        if cleanup is not None:
            track_build_resource(resource, cleanup)


async def prepare_core_runtime(*args, builder: Callable[..., CoreRuntime], **kwargs):
    """Completes sync assembly or closes all partially constructed resources first."""
    async with AsyncExitStack() as cleanup:
        token = _scope.set((cleanup, set()))
        try:
            core = builder(*args, **kwargs)
        finally:
            _scope.reset(token)
        cleanup.pop_all()
        return core


class MemoryBuildResources:
    """Keeps partial allocations in the outer construction scope until host handoff."""

    def __init__(self) -> None:
        self._resources: list[BuildResource] = []
        self._transferred = False

    def register(self, resource: object, cleanup: Callable[[], object]) -> None:
        """Records cleanup immediately, including before a plugin build can return."""
        if self._transferred:
            raise RuntimeError("memory resources already transferred")
        if any(entry.value is resource for entry in self._resources):
            return
        closed = False

        async def close_once():
            nonlocal closed
            if closed:
                return
            closed = True
            result = cleanup()
            if inspect.isawaitable(result):
                await result

        self._resources.append(BuildResource(resource, close_once))
        track_build_resource(resource, close_once)

    def transfer(self) -> list[BuildResource]:
        """Transfers to the returned runtime; outer assembly rollback stays armed."""
        if self._transferred:
            raise RuntimeError("memory resources already transferred")
        self._transferred = True
        return list(self._resources)
