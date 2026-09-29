"""角色会话的上下文划分：用户上下文与外部上下文。

一个角色的所有消息都存放在同一个 ``role:<id>`` 会话里，每条消息带着它所在会话
（thread）的 ``thread_id``。组装模型历史时，按会话把消息分成两类并双向隔离：

- 用户上下文：桌面会话、对方是已绑定用户的渠道私聊，以及没有来源会话的计划任务
  （计划任务由用户安排，结果只会交给用户）。统一会话之前的旧消息没有
  ``thread_id``，它们实际上是桌面对话，同样归入用户上下文。
- 外部上下文：其余所有会话，即全部群聊，以及对方不是已绑定用户的渠道私聊；
  外部会话之间共享同一段上下文。

划分按会话而不是按发送者：已绑定用户在群里的发言属于外部上下文。归属在读取时按
当前的身份绑定计算，绑定或解绑之后，相应私聊的历史随之改变可见性，消息本身不变。
历史组装与主动消息都直接使用本模块，不各写一套规则。桌面聊天界面只显示其中
桌面这一路（``in_desktop_view``），同样由本模块判定。

另一条共享规则按发送者判定：消息是否属于用户本人（``belongs_to_user``）。它在
上下文划分之外，额外认下已绑定用户在群聊等外部会话里的发言。孤独值、在场与
关系快照只看用户本人的消息，不各写一套规则。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from conversation.service import (
    desktop_thread_id,
    is_scheduler_thread,
    network_thread_id,
)
from core.common.message_source import MessageSource
from core.identity import UserIdentity, UserIdentityStore
from session.manager.helpers import role_session_key
from session.manager.models import HistoryFilter, message_thread_id

ContextScope = Literal["user", "external"]


@dataclass(frozen=True)
class UserContextThreads:
    """某角色此刻属于用户上下文的会话。

    ``bound_chat_thread_ids`` 是桌面会话与已绑定用户各已知私聊的会话 ID；
    没有来源会话的计划任务由 ``is_scheduler_thread`` 识别。
    """

    role_id: str
    bound_chat_thread_ids: frozenset[str]

    def contains(self, thread_id: str) -> bool:
        """``thread_id`` 是否属于用户上下文；空值代表统一会话之前的旧消息。"""
        return (
            in_desktop_view(self.role_id, thread_id)
            or thread_id in self.bound_chat_thread_ids
        )


def belongs_to_user(
    message: Mapping[str, Any], user_threads: UserContextThreads
) -> bool:
    """``message`` 是否属于用户本人：唯一的共享判定，调用方不另写规则。

    两种情况成立：消息所在会话属于用户上下文（桌面、已绑定用户的私聊、计划任务、
    没有 ``thread_id`` 的旧消息）；或消息来源记录了发送者是已绑定的用户本人
    （``sender_is_user``，例如用户在群里的发言）。这个标记只在收到消息时为真才
    写入，解绑后依旧保留，按“当时确实是用户本人说的”处理；而会话归属按此刻的
    绑定计算。群友与陌生人的消息两者都不满足。

    对角色自己的消息，这等于“是否在用户上下文里”：它们不带发送者标记。
    """
    if user_threads.contains(message_thread_id(message)):
        return True
    metadata = message.get("metadata")
    if not isinstance(metadata, Mapping):
        return False
    # session_key 只用于补全旧格式来源，这里只读发送者标记。
    return MessageSource.from_metadata(metadata, session_key="").sender_is_user


def in_desktop_view(role_id: str, thread_id: str) -> bool:
    """桌面聊天界面是否显示会话 ``thread_id`` 的消息。

    桌面聊天只显示桌面这一路对话：桌面会话、没有来源会话的计划任务（结果交给
    桌面），以及统一会话之前没有 ``thread_id`` 的旧消息（它们就是桌面对话）。
    渠道私聊与群聊一律不显示，即使对方是已绑定用户。这些会话都属于用户上下文。
    """
    return (
        not thread_id
        or thread_id == desktop_thread_id(role_id)
        or is_scheduler_thread(role_id, thread_id)
    )


def desktop_view_thread_ids(role_id: str, thread_ids: Iterable[str]) -> frozenset[str]:
    """从角色会话已有的 ``thread_ids`` 中挑出桌面聊天显示的那些（见 ``in_desktop_view``）。"""
    return frozenset(
        thread_id for thread_id in thread_ids if in_desktop_view(role_id, thread_id)
    )


def user_context_threads(
    role_id: str, identities: Iterable[UserIdentity]
) -> UserContextThreads:
    """按给定的身份绑定算出角色的用户上下文会话。

    桌面会话之外，已绑定用户的每个已知私聊都按渠道私聊的会话 ID 规则展开。身份
    绑定只记录私聊（配对和后续识别都只登记私聊），所以群聊永远不会落在这里。
    """
    clean_role_id = role_id.strip()
    if not clean_role_id:
        raise ValueError("role_id 不能为空")
    return UserContextThreads(
        role_id=clean_role_id,
        bound_chat_thread_ids=frozenset(
            {
                desktop_thread_id(clean_role_id),
                *(
                    network_thread_id(clean_role_id, chat.channel, chat.chat_id)
                    for identity in identities
                    for chat in identity.chats
                ),
            }
        ),
    )


@dataclass(frozen=True)
class ContextView:
    """一个回合能看到的历史：与回合所在会话同属一类上下文的消息。

    ``user_threads`` 是读取时算出的用户上下文会话；其余会话都属于外部上下文。
    """

    scope: ContextScope
    user_threads: UserContextThreads

    def includes(self, message: Mapping[str, Any]) -> bool:
        """``message`` 是否对本回合可见。"""
        return self.includes_thread(message_thread_id(message))

    def includes_thread(self, thread_id: str) -> bool:
        """会话 ``thread_id`` 的消息是否对本回合可见；空值代表旧消息。"""
        return self.user_threads.contains(thread_id) == (self.scope == "user")


def load_user_context_threads(workspace: Path, role_id: str) -> UserContextThreads:
    """按 ``workspace`` 里当前的身份绑定，读出角色的用户上下文会话。

    身份文件每次查询都重新读取，所以这里新建的存储对象与运行时共享的那一个结果
    一致。
    """
    return user_context_threads(role_id, UserIdentityStore(workspace).list())


def turn_context_view(workspace: Path, role_id: str, thread_id: str) -> ContextView:
    """回合所在会话 ``thread_id`` 对应的历史视图。

    当前回合必须知道自己的会话；只有已存的旧消息才允许没有 ``thread_id``。
    """
    clean_thread_id = thread_id.strip()
    if not clean_thread_id:
        raise ValueError("角色回合缺少 thread_id，无法判定上下文归属")
    user_threads = load_user_context_threads(workspace, role_id)
    scope: ContextScope = (
        "user" if user_threads.contains(clean_thread_id) else "external"
    )
    return ContextView(scope=scope, user_threads=user_threads)


def user_context_view(workspace: Path, role_id: str) -> ContextView:
    """用户上下文的历史视图。

    主动回合组装提示词时使用它（例如收集最近对话）；已提交的主动消息事件则按消息
    所在会话判定上下文，见 ``session_context_view``。
    """
    return ContextView(
        scope="user", user_threads=load_user_context_threads(workspace, role_id)
    )


def session_context_view(
    workspace: Path, *, session_key: str, role_id: str, thread_id: str
) -> ContextView | None:
    """一个回合在会话 ``session_key`` 里的历史视图。

    只有角色共享会话混存多个会话的消息，需要划分；其他会话只有一段对话，
    返回 None，不筛选。历史组装与消息检索工具都经由这里判定。
    """
    if not role_id or session_key != role_session_key(role_id):
        return None
    return turn_context_view(workspace, role_id, thread_id)


def history_filter(view: ContextView | None) -> HistoryFilter | None:
    """``get_history`` 的 ``include`` 参数：有视图时按它筛选，非角色会话不筛选。"""
    return view.includes if view is not None else None
