"""Which generation's affection runtime a caller reads.

Same shape as the reply-policy getter: one object per generation, bound to
that generation's kernel. Unbound callers keep the instance they were given,
so host tests that pass a runtime still reach it. A bound empty socket is
``None`` and every affection side effect is skipped.
"""

from __future__ import annotations

from collections.abc import Callable
from contextvars import ContextVar
from typing import Any

from core.common.runtime_scope import current_runtime_lease
from shiori_sdk.core.affection import Affection


class AffectionGetter:
    """Reads this generation's ``AFFECTION`` after ``bind``."""

    def __init__(self) -> None:
        self._get: Callable[[], Affection | None] | None = None

    @property
    def bound(self) -> bool:
        """Whether ``bind`` has run. An empty socket is a bound ``None``."""
        return self._get is not None

    def bind(self, get: Callable[[], Affection | None]) -> None:
        """Read ``get`` on every later call."""
        self._get = get

    def __call__(self) -> Affection | None:
        if self._get is None:
            raise RuntimeError("好感 getter 尚未绑定到插件内核")
        return self._get()


_turn_getter: ContextVar[AffectionGetter | None] = ContextVar(
    "turn_affection", default=None
)


def bind_turn_affection(getter: AffectionGetter | None):
    """Makes ``getter`` the affection runtime of the current task."""
    return _turn_getter.set(getter)


def reset_turn_affection(token) -> None:
    """Restores the affection getter that was current before binding."""
    _turn_getter.reset(token)


def active_affection_getter() -> AffectionGetter | None:
    """The getter for this task, else the leased generation, else nothing."""
    current = _turn_getter.get()
    if current is not None:
        return current
    lease = current_runtime_lease()
    getter = getattr(getattr(lease, "core", None), "affection", None)
    return getter if isinstance(getter, AffectionGetter) else None


def current_affection(fallback: Any = None) -> Affection | None:
    """The live affection runtime, or ``fallback`` while no getter is bound."""
    getter = active_affection_getter()
    if getter is not None and getter.bound:
        return getter()
    return fallback
