"""Kernel value types: service keys, event verdicts, plugin specs and lifecycle events."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from .diagnostics import PluginDiagnostic

if TYPE_CHECKING:
    from .kernel import Context

type FailurePolicy = Literal["fail_open", "fail_closed"]
"""What an ``on`` handler error does to the chain (§8.1).

``fail_open`` (default) logs the error and passes the event on unchanged;
``fail_closed`` stops the chain and makes ``emit`` return a ``Veto``. An event
type declares it as the class attribute ``on_error: ClassVar[FailurePolicy]``.
"""


class KernelState(StrEnum):
    """Lifecycle states the kernel assigns to a plugin.

    ``PluginDiagnostic.state`` stores the value; hosts may add states of their
    own (trust, admission) in diagnostics the kernel never produces.
    """

    ACTIVE = "ACTIVE"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    REPLACED = "REPLACED"
    STOPPED = "STOPPED"


def plugin_logger(plugin_id: str) -> logging.Logger:
    """The logger behind ``ctx.log``; kernel reports about a plugin go here too."""
    return logging.getLogger(f"shiori.plugin.{plugin_id}")


class Key[T]:
    """Typed identity of a provided service; ``name`` equals the manifest string."""

    __slots__ = ("name",)

    def __init__(self, name: str) -> None:
        if not name or name != name.strip():
            raise ValueError(f"服务 Key 名称不能为空或包含首尾空白: {name!r}")
        self.name = name

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Key) and other.name == self.name

    def __hash__(self) -> int:
        return hash((Key, self.name))

    def __repr__(self) -> str:
        return f"Key({self.name!r})"


@dataclass(frozen=True)
class Veto:
    """Returned by an ``on`` handler (or a core check) to reject the event."""

    reason: str


def failure_policy(event_type: type) -> FailurePolicy:
    """The declared ``on_error`` policy of an event type, ``fail_open`` by default."""
    policy = getattr(event_type, "on_error", "fail_open")
    if policy not in ("fail_open", "fail_closed"):
        raise ValueError(f"{event_type.__name__}.on_error 只能是 fail_open/fail_closed")
    return policy


@dataclass(frozen=True)
class PluginSpec:
    """What the kernel needs to order, set up and reload one plugin.

    ``requires`` / ``optional`` / ``provides`` hold ``Key`` names (manifest
    ``inject`` / ``optional_inject`` / ``provides``); dependency order is derived
    from them. ``runnable`` is false for a register-only spec (disabled, or
    admitted by the host only for bookkeeping — untrusted, invalid contract,
    missing host deps). ``plan`` may still order it and record its keys;
    ``start`` / ``activate`` will not run it, and it does not take part in
    ``conflicts`` / ``replaces`` / duplicate ``provides`` or cycle refusal.
    ``channels`` marks a plugin declaring ``contributes.channels``, which, like
    ``hot_reload=False``, can only change on restart (D14).
    """

    id: str
    setup: Callable[[Context], Awaitable[None]]
    requires: tuple[str, ...] = ()
    optional: tuple[str, ...] = ()
    provides: tuple[str, ...] = ()
    replaces: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    runnable: bool = True
    hot_reload: bool = True
    channels: bool = False
    config: Mapping[str, object] = field(default_factory=dict[str, object])
    data_dir: Path | None = None


@dataclass(frozen=True)
class PluginStarted:
    """A plugin's setup finished; it is ACTIVE."""

    plugin_id: str


@dataclass(frozen=True)
class PluginFailed:
    """A plugin did not start: setup failed (FAILED) or it could not run (BLOCKED)."""

    plugin_id: str
    diagnostic: PluginDiagnostic


@dataclass(frozen=True)
class PluginStopped:
    """A plugin's scope was released (stop, reload or host unload)."""

    plugin_id: str


class KernelError(RuntimeError):
    """A kernel rule rejected an operation; ``plugin_ids`` names who is involved.

    Nothing changed when it is raised, so ``diagnostic.state`` is ``ACTIVE``:
    the refusal itself moves no plugin to another state.
    """

    def __init__(
        self, code: str, stage: str, field: str, reason: str, ids: Iterable[str]
    ) -> None:
        state = KernelState.ACTIVE
        self.diagnostic = PluginDiagnostic(code, stage, field, reason, state=state)
        self.plugin_ids: tuple[str, ...] = tuple(ids)
        super().__init__(reason)
