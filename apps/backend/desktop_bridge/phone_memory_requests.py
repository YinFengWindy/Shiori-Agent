"""Bridge commands behind the phone's chat info page: what the role remembers
about one external conversation (group note, recent activity) and about the
members it met there (member profiles, #499)."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from conversation.context_scope import user_context_threads
from conversation.models import ThreadRecord
from conversation.service import ConversationService
from core.accounts import AccountRegistry
from core.identity import UserIdentityStore
from core.memory.group_environment import GroupEnvironment
from core.memory.member_profiles import MemberKey, MemberProfile, MemberProfiles
from desktop_bridge.phone_requests import (
    required_text,
    role_bound_senders,
    role_channel_thread,
)


def member_row(profile: MemberProfile) -> dict[str, Any]:
    """One member profile as the phone shows it.

    ``nicknames`` is the whole nickname history, most recently used last
    (``call_name`` is that last one, or the ID when none was recorded);
    ``brief`` is the one-line note and ``profile`` the full profile text.
    """
    return {
        "channel": profile.key.channel,
        "sender_id": profile.key.sender_id,
        "call_name": profile.call_name,
        "nicknames": list(profile.nicknames),
        "brief": profile.brief,
        "profile": profile.profile,
    }


class DesktopPhoneMemoryRequestHandler:
    """Reads and edits the role's memory of one external conversation.

    Every request names ``role_id`` and ``thread_id``; the thread must be one
    of the role's current channel conversations outside the user context (a
    bound user's private chat has no chat info page). Stores are the owning
    modules shared with memory consolidation.

    - ``phone.conversation.note`` returns ``{"thread_id", "note"}``, the group
      note Markdown (``""`` when there is none); ``phone.conversation.note.save``
      with ``note`` replaces it (a blank note removes it) and returns the same.
    - ``phone.conversation.activity`` returns ``{"thread_id",
      "recent_activity"}``, read-only: only consolidation writes it.
    - ``phone.conversation.members`` returns ``{"thread_id", "members"}``:
      ``member_row`` of every member with a profile who spoke in the
      conversation, by name, leaving out anyone a current binding recognises as
      the user.
    - ``phone.member.profile`` with ``sender_id`` returns ``{"member"}`` (None
      when the member has no profile); ``phone.member.profile.save`` with
      ``brief`` and ``profile`` rewrites those two fields of an existing
      profile and returns it; ``phone.member.profile.delete`` deletes it. The
      member is ``sender_id`` on the conversation's channel; the user has no
      member profile, so naming the user is an error.
    """

    def __init__(
        self,
        *,
        conversations: ConversationService,
        accounts: AccountRegistry,
        identities: UserIdentityStore,
        group_environment: GroupEnvironment,
        members: MemberProfiles,
    ) -> None:
        self._conversations = conversations
        self._accounts = accounts
        self._identities = identities
        self._group_environment = group_environment
        self._members = members

    async def handle(
        self, method: str, payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Handles one chat info request; None for methods it does not own."""
        if method == "phone.conversation.note":
            role_id, thread = self._external_thread(payload)
            return self._note(role_id, thread)
        if method == "phone.conversation.note.save":
            role_id, thread = self._external_thread(payload)
            note = payload.get("note")
            if not isinstance(note, str):
                raise ValueError("note 必须是文本")
            self._group_environment.write_note(role_id, thread.id, note)
            return self._note(role_id, thread)
        if method == "phone.conversation.activity":
            role_id, thread = self._external_thread(payload)
            snapshot = self._group_environment.read(role_id, thread.id)
            return {"thread_id": thread.id, "recent_activity": snapshot.recent_activity}
        if method == "phone.conversation.members":
            role_id, thread = self._external_thread(payload)
            return {
                "thread_id": thread.id,
                "members": self._member_rows(role_id, thread),
            }
        if method == "phone.member.profile":
            role_id, key = self._member(payload)
            profile = self._members.read(role_id, key)
            return {"member": member_row(profile) if profile is not None else None}
        if method == "phone.member.profile.save":
            role_id, key = self._member(payload)
            brief, text = payload.get("brief"), payload.get("profile")
            if not isinstance(brief, str) or not isinstance(text, str):
                raise ValueError("brief 与 profile 必须是文本")
            existing = self._members.read(role_id, key)
            if existing is None:
                raise LookupError("该成员还没有档案")
            saved = replace(existing, brief=brief.strip(), profile=text.strip())
            self._members.write(role_id, saved)
            return {"member": member_row(saved)}
        if method == "phone.member.profile.delete":
            role_id, key = self._member(payload)
            self._members.delete(role_id, key)
            return {"channel": key.channel, "sender_id": key.sender_id}
        return None

    def _external_thread(self, payload: dict[str, Any]) -> tuple[str, ThreadRecord]:
        """The request's role and conversation; fails unless it is external."""
        role_id = required_text(payload, "role_id")
        thread = role_channel_thread(
            self._conversations, role_id, required_text(payload, "thread_id")
        )
        if thread is None:
            raise ValueError("会话不属于该角色")
        if user_context_threads(role_id, self._identities.list()).contains(thread.id):
            raise ValueError("用户上下文会话没有群信息")
        return role_id, thread

    def _member(self, payload: dict[str, Any]) -> tuple[str, MemberKey]:
        """The request's role and member (``sender_id`` on the thread's channel)."""
        role_id, thread = self._external_thread(payload)
        key = MemberKey(
            channel=thread.channel, sender_id=required_text(payload, "sender_id")
        )
        bound = role_bound_senders(
            role_id, accounts=self._accounts, identities=self._identities
        )
        if key.is_user(bound):
            raise ValueError("用户本人没有成员档案")
        return role_id, key

    def _note(self, role_id: str, thread: ThreadRecord) -> dict[str, Any]:
        return {
            "thread_id": thread.id,
            "note": self._group_environment.read_note(role_id, thread.id),
        }

    def _member_rows(self, role_id: str, thread: ThreadRecord) -> list[dict[str, Any]]:
        bound = role_bound_senders(
            role_id, accounts=self._accounts, identities=self._identities
        )
        profiles = [
            profile
            for profile in self._members.list(role_id, thread_id=thread.id)
            if not profile.key.is_user(bound)
        ]
        profiles.sort(key=lambda profile: profile.call_name)
        return [member_row(profile) for profile in profiles]
