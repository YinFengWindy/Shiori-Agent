"""Which generation's natural-chat policy a turn reads.

The getter is owned by one runtime generation and bound to that generation's
kernel. Turns set it for their task. Desktop admission and proactive drafts
that already hold the runtime lease read the same object from the lease.
Before anything is bound, the role flag alone still selects the core
multi-message protocol, so a core-only turn keeps working. Once bound, a
missing provider forces a single reply even if the role flag is on.
Prompt text is read only from a bound policy.
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


def natural_chat_selected(role: RoleRecord | None) -> bool:
    """Whether this turn uses the natural-chat prompts and sequence admission.

    Unbound, the role flag is the protocol switch. Bound, the plugin must be
    present as well: a disabled plugin does not select, and the reply stays
    one message.
    """
    flag = natural_chat_enabled(role)
    getter = active_reply_policy_getter()
    if getter is None or not getter.bound:
        return flag
    return getter() is not None and flag


def natural_chat_passive_prompt() -> str | None:
    """The chat prompt, only when a policy is bound and present."""
    getter = active_reply_policy_getter()
    if getter is None or not getter.bound:
        return None
    policy = getter()
    if policy is None:
        return None
    return policy.passive_prompt()


def natural_chat_draft_prompt() -> str | None:
    """The proactive draft prompt, only when a policy is bound and present."""
    getter = active_reply_policy_getter()
    if getter is None or not getter.bound:
        return None
    policy = getter()
    if policy is None:
        return None
    return policy.draft_prompt()
