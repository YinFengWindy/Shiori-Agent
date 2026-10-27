"""Tracks resources allocated before a complete CoreRuntime owns their lifetime."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from contextlib import AsyncExitStack
from contextvars import ContextVar
from typing import TYPE_CHECKING, TypeVar

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
