"""Bound per-generation getters for host tests that assemble the core by hand.

Production binds both getters to the generation's plugin kernel. A test that
builds a loop, a desktop bridge or a phase without a kernel binds them here:
``None`` is the empty socket (plugin off), anything else stands in for the
plugin's service.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from core.roles.affection_access import (
    AffectionGetter,
    bind_turn_affection,
    reset_turn_affection,
)
from core.roles.reply_policy import (
    ReplyPolicyGetter,
    bind_turn_reply_policy,
    reset_turn_reply_policy,
)


def bound_affection(runtime: Any = None) -> AffectionGetter:
    """An affection getter that always reads ``runtime``."""
    getter = AffectionGetter()
    getter.bind(lambda: runtime)
    return getter


def bound_reply_policy(policy: Any = None) -> ReplyPolicyGetter:
    """A reply-policy getter that always reads ``policy``."""
    getter = ReplyPolicyGetter()
    getter.bind(lambda: policy)
    return getter


@contextmanager
def turn_getters(*, affection: Any = None, policy: Any = None) -> Iterator[None]:
    """Binds both getters to the current task, as the loop does for a turn."""
    affection_token = bind_turn_affection(bound_affection(affection))
    policy_token = bind_turn_reply_policy(bound_reply_policy(policy))
    try:
        yield
    finally:
        reset_turn_reply_policy(policy_token)
        reset_turn_affection(affection_token)


def run_in_turn[T](
    target: T, *, affection: Any = None, policy: Any = None, method: str = "run"
) -> T:
    """``target`` whose async ``method`` binds the getters around each call.

    For a phase, pipeline or reasoner a test drives without the loop, which
    binds them per turn in production.
    """
    run = getattr(target, method)

    async def bound_run(*args: Any, **kwargs: Any) -> Any:
        with turn_getters(affection=affection, policy=policy):
            return await run(*args, **kwargs)

    setattr(target, method, bound_run)
    return target
