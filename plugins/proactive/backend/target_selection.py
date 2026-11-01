"""Chooses the one session a proactive message is delivered to.

Each proactive message is sent exactly once. The choice follows where the user
most likely is right now:

1. the desktop, when it is a candidate and the user is at it;
2. otherwise the non-desktop candidate the user last wrote in;
3. with no user message in any of them, the first non-desktop candidate;
4. with no non-desktop candidate, the desktop.

``select_proactive_target`` is the pure rule; ``ProactiveTargetResolver`` reads
its inputs (the role's candidate chats, desktop presence and the last user
message per candidate thread) through ``PROACTIVE_HOST``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime

from shiori_sdk.core.proactive_host import CandidateChat, ProactiveHost
from shiori_sdk.roles import Roles

# The desktop chat's channel (see ``InitiatedReply``).
DESKTOP_CHANNEL = "desktop"


def select_proactive_target(
    candidates: Sequence[CandidateChat],
    *,
    desktop_present: bool,
    last_user_at: Mapping[CandidateChat, datetime],
) -> CandidateChat:
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
    come from ``PROACTIVE_HOST``. The role's ``proactive`` settings on
    ``ROLES`` decide whether it is eligible at all.
    """

    def __init__(self, *, roles: Roles, host: ProactiveHost) -> None:
        self._roles = roles
        self._host = host

    def resolve_saved(self, role_id: str) -> CandidateChat | None:
        """Selects among the role's candidates; None when proactive is disabled.

        The settings are read now, so a switch edit applies on the next call.
        The candidates are the desktop session and the private chats with the
        bound user through the role's online accounts, so the desktop keeps
        the message while the user is at it or no such chat exists.
        """
        settings = self._roles.plugin_settings(role_id, "proactive").read()
        if not settings.get("enabled"):
            return None
        return self.resolve(role_id, self._host.candidate_chats(role_id))

    def resolve(
        self, role_id: str, candidates: Sequence[CandidateChat]
    ) -> CandidateChat:
        """Selects the target among ``candidates`` of ``role_id`` right now."""
        return select_proactive_target(
            candidates,
            desktop_present=self._host.user_at_desktop(),
            last_user_at=self._last_user_times(role_id, candidates),
        )

    def _last_user_times(
        self, role_id: str, candidates: Sequence[CandidateChat]
    ) -> dict[CandidateChat, datetime]:
        times: dict[CandidateChat, datetime] = {}
        for candidate in candidates:
            if candidate.channel == DESKTOP_CHANNEL:
                continue
            when = self._host.last_user_message_at(
                role_id, candidate.channel, candidate.chat_id
            )
            if when is not None:
                times[candidate] = when
        return times
