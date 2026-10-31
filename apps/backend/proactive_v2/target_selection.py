"""Chooses the one session a proactive message is delivered to.

Each proactive message is sent exactly once. The choice follows where the user
most likely is right now:

1. the desktop, when it is a candidate and the user is at it;
2. otherwise the non-desktop candidate the user last wrote in;
3. with no user message in any of them, the first non-desktop candidate;
4. with no non-desktop candidate, the desktop.

``select_proactive_target`` is the pure rule; ``ProactiveTargetResolver`` reads
its inputs (desktop presence, last user message per candidate thread) for the
proactive runtime and the desktop preview alike, so both always agree.

A role's own candidates are its desktop session followed by every private chat
with the bound user (``core.identity``) through one of the role's online
accounts (``core.roles.bound_chats``). A chosen private chat is reached
through that account (``ProactiveTargetResolver.bound_chat_target``).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime

from shiori_sdk.accounts.targets import AccountTarget
from shiori_sdk.core.proactive_host import ProactiveHost
from core.common.channel_directory import DESKTOP_CHANNEL
from core.roles.models import RoleProactiveCandidate
from core.roles.store import RoleStore


def select_proactive_target(
    candidates: Sequence[RoleProactiveCandidate],
    *,
    desktop_present: bool,
    last_user_at: Mapping[RoleProactiveCandidate, datetime],
) -> RoleProactiveCandidate:
    """Returns the single candidate to deliver to.

    ``candidates`` are in binding order; ``last_user_at`` holds the newest user
    message time of the non-desktop candidates that have one. Raises
    ``ValueError`` when there is no candidate at all.
    """
    if not candidates:
        raise ValueError("主动推送没有可用的接收会话")
    desktop = next(
        (item for item in candidates if item.channel == DESKTOP_CHANNEL), None
    )
    if desktop is not None and desktop_present:
        return desktop
    external = [item for item in candidates if item.channel != DESKTOP_CHANNEL]
    answered = [item for item in external if item in last_user_at]
    if answered:
        # max keeps the first of equal times, i.e. the earlier binding.
        return max(answered, key=lambda item: last_user_at[item])
    if external:
        return external[0]
    # Only the desktop is a candidate: it keeps the message even while away.
    return candidates[0]


class ProactiveTargetResolver:
    """Reads the live inputs of ``select_proactive_target`` for a role.

    Candidate chats, the last user message on a thread and desktop presence
    come from ``PROACTIVE_HOST``. ``roles`` is the runtime's shared store: its
    proactive switch decides whether a saved role is eligible.
    """

    def __init__(self, *, roles: RoleStore, host: ProactiveHost) -> None:
        self._roles = roles
        self._host = host

    def resolve_saved(self, role_id: str) -> RoleProactiveCandidate | None:
        """Selects among the role's candidates; None when proactive is disabled.

        The candidates are the desktop session and the private chats with the
        bound user through the role's online accounts, so the desktop keeps
        the message while the user is at it or no such chat exists.
        """
        role = self._roles.get_role(role_id)
        if role is None:
            raise KeyError(f"角色不存在: {role_id}")
        if not role.proactive.enabled:
            return None
        candidates = [
            RoleProactiveCandidate(chat.channel, chat.chat_id)
            for chat in self._host.candidate_chats(role_id)
        ]
        return self.resolve(role_id, candidates)

    def bound_chat_target(
        self, role_id: str, channel: str, chat_id: str
    ) -> tuple[str, AccountTarget]:
        """The account channel and private target reaching a bound user's chat.

        ``channel`` / ``chat_id`` name a candidate ``resolve_saved`` chose.
        """
        return self._host.bound_chat_target(role_id, channel, chat_id)

    def resolve(
        self, role_id: str, candidates: Sequence[RoleProactiveCandidate]
    ) -> RoleProactiveCandidate:
        """Selects the target among ``candidates`` of ``role_id`` right now."""
        return select_proactive_target(
            candidates,
            desktop_present=self._host.user_at_desktop(),
            last_user_at=self._last_user_times(role_id, candidates),
        )

    def _last_user_times(
        self, role_id: str, candidates: Sequence[RoleProactiveCandidate]
    ) -> dict[RoleProactiveCandidate, datetime]:
        times: dict[RoleProactiveCandidate, datetime] = {}
        for candidate in candidates:
            if candidate.channel == DESKTOP_CHANNEL:
                continue
            when = self._host.last_user_message_at(
                role_id, candidate.channel, candidate.chat_id
            )
            if when is not None:
                times[candidate] = when
        return times
