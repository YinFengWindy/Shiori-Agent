"""Read lifecycle evidence without owning or repairing plugin resources."""

from __future__ import annotations

import asyncio
import functools
import socket
import sqlite3
import subprocess

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import patch

import httpx

from bootstrap.tools import CoreRuntime
from shiori_sdk.core.services import CHANNELS
from shiori_sdk.kernel import Kernel, Scope

_ACTIVATING: ContextVar[str | None] = ContextVar("contract_activating", default=None)


def handler_name(handler: Any) -> str:
    """Stable callable identity; generation namespaces and addresses are not identities."""
    while isinstance(handler, functools.partial):
        handler = handler.func
    return getattr(handler, "__qualname__", type(handler).__qualname__)


def snapshot(core: CoreRuntime) -> dict[str, Any]:
    """Read production registries in their dispatch/registration order."""
    manager = core.plugin_manager
    assert manager is not None
    kernel = manager.kernel
    rank = {name: n for n, name in enumerate(kernel.order())}

    def subscriptions(table):
        return tuple(
            (
                kind.__qualname__,
                tuple(
                    (item.plugin_id, handler_name(item.handler))
                    for item in sorted(
                        entries,
                        key=lambda item: (rank.get(item.plugin_id, -1), item.seq),
                    )
                ),
            )
            for kind, entries in table.items()
            if entries
        )

    channels = kernel.get(CHANNELS)
    return {
        "providers": tuple(
            (key, owner) for key, (owner, _) in kernel._providers.items() if owner
        ),
        "on": subscriptions(kernel._events._on),
        "watch": subscriptions(kernel._events._watch),
        "rpc": tuple(
            (
                name,
                entry.plugin_id,
                entry.policy.concurrency,
                entry.policy.admission_exempt,
            )
            for name, entry in core.plugin_rpc._entries.items()
        ),
        "services": tuple(
            (key, entry.descriptor["contract"], tuple(entry.methods))
            for key, entry in core.plugin_rpc.services._entries.items()
        ),
        "tools": tuple(core.tools._tools),
        "bus": tuple(
            (kind.__qualname__, tuple(map(handler_name, entries)))
            for kind, entries in core.event_bus._handlers.items()
            if entries
        ),
        "channels": tuple(
            (pid, tuple(getattr(channel, "name", "") for channel in values))
            for pid, values in channels._by_plugin.items()
            if values
        ),
    }


def assert_snapshot(actual: dict[str, Any], expected: dict[str, Any]) -> None:
    """Explain the exact registration category that diverged, including order."""
    assert actual == expected, {
        key: {"expected": expected[key], "actual": actual[key]}
        for key in expected
        if actual[key] != expected[key]
    }


@dataclass
class LifecycleObservation:
    """Observations only; emergency cancellation happens after the verdict."""

    registrations: list[tuple[str, bool, str]] = field(default_factory=list)
    spawned: list[tuple[str, str, asyncio.Task[Any]]] = field(default_factory=list)
    tasks: list[asyncio.Task[Any]] = field(default_factory=list)
    connections: list[sqlite3.Connection] = field(default_factory=list)
    unexpected_io: list[str] = field(default_factory=list)

    def registration_order(self) -> list[tuple[str, bool, str]]:
        """Scope closes subscriptions before LIFO effects, even across publication."""
        return [entry for entry in self.registrations if entry[1]] + [
            entry for entry in self.registrations if not entry[1]
        ]

    def assert_closed(self) -> None:
        """A bare task and a failed detached task both fail the contract."""
        assert not [
            t for t in self.tasks if not t.done()
        ], "plugin task outlived disposal"
        assert not self.unexpected_io, self.unexpected_io
        for connection in self.connections:
            try:
                _ = connection.in_transaction
            except sqlite3.ProgrammingError as error:
                assert "closed" in str(error), str(error)
            else:
                raise AssertionError("plugin SQLite connection outlived disposal")
        errors = [t.exception() for t in self.tasks if not t.cancelled()]
        assert not [e for e in errors if e is not None], errors

    async def emergency_cleanup(self) -> None:
        """Run only in fixture teardown, after any failed lifecycle assertion."""
        pending = [t for t in self.tasks if not t.done()]
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        for connection in self.connections:
            try:
                connection.close()
            except sqlite3.ProgrammingError:
                # A thread-owned connection was already judged above; teardown
                # cannot relocate its ownership to the event-loop thread.
                pass


@contextmanager
def observe_lifecycle() -> Iterator[LifecycleObservation]:
    """Observe original kernel/scope calls without replacing their behavior."""
    observation = LifecycleObservation()
    original_add, original_activate = Scope._add, Kernel.activate
    original_connect = sqlite3.connect
    loop = asyncio.get_running_loop()
    original_factory = loop.get_task_factory()

    def scope_add(scope, entry):
        observation.registrations.append((scope.owner, entry.subscription, entry.label))
        return original_add(scope, entry)

    async def activate(kernel, plugin_id):
        token = _ACTIVATING.set(plugin_id)
        try:
            return await original_activate(kernel, plugin_id)
        finally:
            _ACTIVATING.reset(token)

    def task_factory(event_loop, coro, **kwargs):
        task = (
            original_factory(event_loop, coro, **kwargs)
            if original_factory
            else asyncio.Task(coro, loop=event_loop, **kwargs)
        )
        observation.tasks.append(task)
        owner = _ACTIVATING.get()
        # CPython schedules async-generator finalizers using the context active
        # at GC time. They are still tracked above for leaks and exceptions, but
        # that inherited activation is not evidence of a plugin-authored spawn.
        finalizer = (
            type(coro).__module__ == "builtins"
            and type(coro).__name__ == "async_generator_athrow"
        )
        if owner is not None and not finalizer:
            observation.spawned.append(
                (owner, getattr(coro, "__qualname__", type(coro).__name__), task)
            )
        return task

    def connect(*args, **kwargs):
        connection = original_connect(*args, **kwargs)
        observation.connections.append(connection)
        return connection

    def denied_io(*args, **kwargs):
        observation.unexpected_io.append(
            "Unexpected network/process call in setup lifecycle"
        )
        raise AssertionError(observation.unexpected_io[-1])

    async def denied_http(*args, **kwargs):
        denied_io(*args, **kwargs)

    loop.set_task_factory(task_factory)
    try:
        with (
            patch.object(Scope, "_add", scope_add),
            patch.object(Kernel, "activate", activate),
            patch.object(sqlite3, "connect", connect),
            patch.object(socket.socket, "connect", denied_io),
            patch.object(socket.socket, "connect_ex", denied_io),
            # Keep the class intact for dependency annotations such as
            # Popen[bytes]; block construction before any process can start.
            patch.object(subprocess.Popen, "__init__", denied_io),
            patch.object(httpx.AsyncClient, "send", denied_http),
        ):
            yield observation
    finally:
        loop.set_task_factory(original_factory)


def retained_tasks(resources: dict[Any, Any]) -> set[asyncio.Task[Any]]:
    """Tasks actually held by process resources, excluding references into the host."""
    found: set[asyncio.Task[Any]] = set()
    seen: set[int] = set()

    def visit(value):
        if id(value) in seen:
            return
        seen.add(id(value))
        if isinstance(value, asyncio.Task):
            found.add(value)
        elif isinstance(value, dict):
            for item in value.values():
                visit(item)
        elif isinstance(value, (list, tuple, set, frozenset)):
            for item in value:
                visit(item)
        elif type(value).__module__.startswith(("akasic_plugin_", "plugins.")):
            for item in vars(value).values():
                visit(item)

    for resource in resources.values():
        visit(resource)
    return found
