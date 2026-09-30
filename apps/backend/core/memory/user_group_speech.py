"""「用户最近在群里说过」：用户回合附带的用户本人在群里的最近原文（#539）。

用户在群里说的话属于外部上下文，桌面与私聊回合看不到它的原文；这一块把用户本人
最近 ``USER_GROUP_SPEECH_WINDOW`` 内在各群的发言（至多 ``USER_GROUP_SPEECH_LIMIT``
条）与角色对它们的回复带进用户上下文回合，标明群名，不含群友的发言。它单独成块，
不并入对话历史的时间线。

来源有两处：角色会话里群聊的用户发言（@ 或回复角色、触发了回合的那些）及其后
角色在同一群的回复；以及旁听记录里用户本人的发言（没有叫角色，所以没有回复）。
"用户本人"看消息收到时记下的 ``sender_is_user``。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from conversation.service import role_thread_prefix
from conversation.store import ConversationStore
from core.common.channel_chat_types import is_group_chat_type
from core.common.message_source import MessageSource
from session.manager.helpers import role_session_key, truncate_text

# 往前看多久、至多几条用户发言，以及用户发言与角色回复各自的截断长度。
USER_GROUP_SPEECH_WINDOW = timedelta(hours=6)
USER_GROUP_SPEECH_LIMIT = 10
USER_GROUP_SPEECH_CHAR_LIMIT = 200


@dataclass(frozen=True)
class UserGroupSpeech:
    """用户在某个群的一条发言；``reply`` 是角色随后在该群的回复，没有时为空串。"""

    at: datetime
    group: str
    text: str
    reply: str = ""


def collect_user_group_speech(
    store: ConversationStore, role_id: str, *, now: datetime
) -> list[UserGroupSpeech]:
    """``now`` 之前 ``USER_GROUP_SPEECH_WINDOW`` 内用户本人在各群的发言，旧的在前。

    至多 ``USER_GROUP_SPEECH_LIMIT`` 条，超出时留最近的。
    """
    since = now - USER_GROUP_SPEECH_WINDOW
    speeches = _addressed_speeches(
        store.thread_messages_since(role_session_key(role_id), since)
    )
    for heard in store.listening.sent_by_user_since(role_thread_prefix(role_id), since):
        source = MessageSource.from_metadata(
            {"message_source": heard.source}, session_key=""
        )
        speeches.append(
            UserGroupSpeech(
                at=datetime.fromisoformat(heard.timestamp),
                group=_group_label(source),
                text=heard.content,
            )
        )
    speeches.sort(key=lambda speech: speech.at)
    return speeches[-USER_GROUP_SPEECH_LIMIT:]


def render_user_group_speech(speeches: Sequence[UserGroupSpeech]) -> str:
    """用户回合注入的「用户最近在群里说过」段落；没有发言时为空串。"""
    if not speeches:
        return ""
    hours = int(USER_GROUP_SPEECH_WINDOW.total_seconds() // 3600)
    lines = [
        "## 用户最近在群里说过",
        f"（最近 {hours} 小时，只有用户本人的发言与我的回复）",
    ]
    for speech in speeches:
        text = truncate_text(speech.text.strip(), USER_GROUP_SPEECH_CHAR_LIMIT)
        lines.append(
            f"- {speech.at.strftime('%m-%d %H:%M')} {speech.group} 用户：{text}"
        )
        if speech.reply:
            reply = truncate_text(speech.reply.strip(), USER_GROUP_SPEECH_CHAR_LIMIT)
            lines.append(f"  我的回复：{reply}")
    return "\n".join(lines)


def _addressed_speeches(
    messages: Sequence[Mapping[str, Any]],
) -> list[UserGroupSpeech]:
    """角色会话里用户本人在群里的发言，各带角色随后在同一群的回复。"""
    speeches: list[UserGroupSpeech] = []
    for index, message in enumerate(messages):
        if message["role"] != "user":
            continue
        source = MessageSource.from_metadata(message["metadata"], session_key="")
        if not source.sender_is_user or not is_group_chat_type(source.chat_type):
            continue
        speeches.append(
            UserGroupSpeech(
                at=datetime.fromisoformat(message["ts"]),
                group=_group_label(source),
                text=message["content"],
                reply=_reply_after(messages, index),
            )
        )
    return speeches


def _reply_after(messages: Sequence[Mapping[str, Any]], index: int) -> str:
    """第 ``index`` 条消息之后、同一群下一条来信之前角色的回复；没有时为空串。"""
    thread_id = messages[index]["thread_id"]
    for message in messages[index + 1 :]:
        if message["thread_id"] != thread_id:
            continue
        if message["role"] == "user":
            return ""
        if message["role"] == "assistant" and not message["proactive"]:
            if message["content"]:
                return str(message["content"])
    return ""


def _group_label(source: MessageSource) -> str:
    return f"群「{source.group_name or source.chat_id or '未知群'}」"
