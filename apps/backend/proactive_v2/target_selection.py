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
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime

from conversation.service import desktop_chat_id, network_thread_id
from conversation.store import ConversationStore
from core.common.channel_directory import DESKTOP_CHANNEL
from core.desktop_presence import DesktopPresence
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
    """Reads the live inputs of ``select_proactive_target`` for a role."""

    def __init__(
        self,
        *,
        roles: RoleStore,
        conversations: ConversationStore,
        desktop_presence: DesktopPresence,
    ) -> None:
        self._roles = roles
        self._conversations = conversations
        self._desktop_presence = desktop_presence

    def resolve_saved(self, role_id: str) -> RoleProactiveCandidate | None:
        """Starts proactive turns in the role's desktop session."""
        role = self._roles.get_role(role_id)
        if role is None:
            raise KeyError(f"角色不存在: {role_id}")
        if not role.proactive.enabled:
            return None
        return RoleProactiveCandidate(DESKTOP_CHANNEL, desktop_chat_id(role_id))

    def resolve(
        self, role_id: str, candidates: Sequence[RoleProactiveCandidate]
    ) -> RoleProactiveCandidate:
        """Selects the target among ``candidates`` of ``role_id`` right now."""
        return select_proactive_target(
            candidates,
            desktop_present=self._desktop_presence.is_desktop_present(),
            last_user_at=self._last_user_times(role_id, candidates),
        )

    def _last_user_times(
        self, role_id: str, candidates: Sequence[RoleProactiveCandidate]
    ) -> dict[RoleProactiveCandidate, datetime]:
        times: dict[RoleProactiveCandidate, datetime] = {}
        for candidate in candidates:
            if candidate.channel == DESKTOP_CHANNEL:
                continue
            raw = self._conversations.last_user_message_at(
                network_thread_id(role_id, candidate.channel, candidate.chat_id)
            )
            if raw is not None:
                # A naive legacy timestamp was written in local time.
                times[candidate] = datetime.fromisoformat(raw).astimezone()
        return times
