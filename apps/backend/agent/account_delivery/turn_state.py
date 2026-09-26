"""Turn-local signal preventing a second implicit send after explicit delivery."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_delivery_state: ContextVar[dict[str, bool] | None] = ContextVar(
    "account_delivery_state", default=None
)


@contextmanager
def account_delivery_scope(state: dict[str, bool]) -> Iterator[None]:
    """Bind one model attempt's delivery signal without exposing tool kwargs."""
    token = _delivery_state.set(state)
    try:
        yield
    finally:
        _delivery_state.reset(token)


def mark_account_delivery_sent() -> None:
    """Suppress the implicit reply once a platform reports accepting a send."""
    state = _delivery_state.get()
    if state is not None:
        state["sent"] = True
