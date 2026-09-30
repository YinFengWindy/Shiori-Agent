"""群聊旁听的开关与上限（#538）。

只作用于角色当前的渠道群聊，且渠道须由插件声明支持旁听（manifest 渠道声明的
``group_listening``）。小手机（用户）与设置旁听的工具（角色，#540）共用这里的
校验，再写入 ``GroupListeningStore``。
"""

from __future__ import annotations

from collections.abc import Callable

from conversation.listening_store import GroupListeningStore
from conversation.listening_switches import ListeningOperator, ListeningSettings
from conversation.models import ThreadRecord
from conversation.service import ConversationService
from core.common.channel_chat_types import CHAT_TYPE_GROUP, ChatType


class GroupListeningControl:
    """Checks that a role's conversation can be listened to before changing it.

    ``supports_channel`` answers whether a channel's plugin declares group
    listening support.
    """

    def __init__(
        self,
        conversations: ConversationService,
        supports_channel: Callable[[str], bool],
    ) -> None:
        self._conversations = conversations
        self._supports_channel = supports_channel

    @property
    def store(self) -> GroupListeningStore:
        """Where the listening records and switches are kept."""
        return self._conversations.listening

    def supports(self, channel: str, chat_type: ChatType | None) -> bool:
        """Whether a conversation of ``chat_type`` on ``channel`` can be listened to.

        Only a group, on a channel whose plugin declares listening support.
        """
        return chat_type == CHAT_TYPE_GROUP and self._supports_channel(channel)

    def current_thread(self, thread_id: str) -> ThreadRecord | None:
        """``thread_id`` while it is one of its role's channel conversations."""
        thread = self._conversations.get_thread(thread_id)
        if thread is None:
            return None
        return self._conversations.role_channel_thread(thread.role_id, thread.id)

    def group(self, role_id: str, thread_id: str) -> ThreadRecord:
        """The role's group ``thread_id``; fails unless it can be listened to."""
        thread = self._conversations.role_channel_thread(role_id, thread_id)
        if thread is None:
            raise ValueError("会话不属于该角色")
        chat_type = self._conversations.thread_chat_types([thread.id])[thread.id]
        if not self.supports(thread.channel, chat_type):
            raise ValueError("该会话不支持旁听")
        return thread

    def set_enabled(
        self,
        role_id: str,
        thread_id: str,
        enabled: bool,
        *,
        operator: ListeningOperator,
    ) -> ListeningSettings:
        """Turns listening on or off for one of the role's groups, logging ``operator``."""
        thread = self.group(role_id, thread_id)
        return self.store.switches.set_enabled(thread.id, enabled, operator=operator)

    def set_daily_cap(
        self, role_id: str, thread_id: str, cap: object
    ) -> ListeningSettings:
        """Overrides the group's daily cap; None follows the global default.

        ``cap`` is checked by the switches (an integer of at least 1).
        """
        thread = self.group(role_id, thread_id)
        return self.store.switches.set_daily_cap(thread.id, cap)
