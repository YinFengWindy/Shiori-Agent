"""Which generation's natural-chat policy a turn reads.

The getter is owned by one runtime generation and bound to that generation's
kernel. Turns set it for their task. Desktop admission and proactive drafts
that already hold the runtime lease read the same object from the lease.
Reading before anything is bound raises. Once bound, a missing provider
forces a single reply even if the role flag is on.
"""

from __future__ import annotations

from collections.abc import Callable
from contextvars import ContextVar

from core.common.runtime_scope import current_runtime_lease
from core.roles.models import RoleRecord
from core.roles.natural_chat import natural_chat_enabled
from shiori_sdk.core.reply_policy import ReplyPolicy


class ReplyPolicyGetter:
    """Reads this generation's ``REPLY_POLICY`` after ``bind``."""

    def __init__(self) -> None:
        self._get: Callable[[], ReplyPolicy | None] | None = None

    @property
    def bound(self) -> bool:
        """Whether ``bind`` has run. An empty socket is a bound ``None``."""
        return self._get is not None

    def bind(self, get: Callable[[], ReplyPolicy | None]) -> None:
        """Read ``get`` on every later call."""
        self._get = get

    def __call__(self) -> ReplyPolicy | None:
        if self._get is None:
            raise RuntimeError("即时聊天策略 getter 尚未绑定到插件内核")
        return self._get()


_turn_getter: ContextVar[ReplyPolicyGetter | None] = ContextVar(
    "turn_reply_policy", default=None
)


def bind_turn_reply_policy(getter: ReplyPolicyGetter | None):
    """Makes ``getter`` the policy of the current task and its children."""
    return _turn_getter.set(getter)


def reset_turn_reply_policy(token) -> None:
    """Restores the policy that was current before ``bind_turn_reply_policy``."""
    _turn_getter.reset(token)


def active_reply_policy_getter() -> ReplyPolicyGetter | None:
    """The getter for this task, else the leased generation, else nothing."""
    current = _turn_getter.get()
    if current is not None:
        return current
    lease = current_runtime_lease()
    getter = getattr(getattr(lease, "core", None), "reply_policy", None)
    return getter if isinstance(getter, ReplyPolicyGetter) else None


def _current_policy() -> ReplyPolicy | None:
    """This task's bound policy, ``None`` for an empty socket.

    Raises when no getter is reachable or it is not bound yet: deciding the
    protocol before the generation's plugins are known is a wiring bug.
    """
    getter = active_reply_policy_getter()
    if getter is None:
        raise RuntimeError("当前任务没有可用的即时聊天策略 getter")
    return getter()


def natural_chat_selected(role: RoleRecord | None) -> bool:
    """Whether this turn uses the natural-chat prompts and sequence admission.

    Both the plugin and the role flag must be on (P3-9 table). A disabled
    plugin does not select, and the reply stays one message.
    """
    return _current_policy() is not None and natural_chat_enabled(role)


def natural_chat_passive_prompt() -> str | None:
    """The chat prompt, or ``None`` while the plugin is off."""
    policy = _current_policy()
    return policy.passive_prompt() if policy is not None else None


def natural_chat_draft_prompt() -> str | None:
    """The proactive draft prompt, or ``None`` while the plugin is off."""
    policy = _current_policy()
    return policy.draft_prompt() if policy is not None else None
