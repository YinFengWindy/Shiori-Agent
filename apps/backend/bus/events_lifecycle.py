from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from shiori_sdk.tool_chain import ToolCallGroup


def _empty_media() -> list[str]:
    return []


def _empty_metadata() -> dict[str, Any]:
    return {}


def _empty_int_metadata() -> dict[str, int]:
    return {}


def _empty_skill_names() -> list[str]:
    return []


def _empty_tool_chain() -> list[dict[str, Any]]:
    return []


def _empty_tool_call_groups() -> list["ToolCallGroup"]:
    return []


@dataclass
class BeforeReasoning:
    session_key: str
    channel: str
    chat_id: str
    content: str
    skill_names: list[str] = field(default_factory=_empty_skill_names)
    retrieved_memory_block: str = ""
    role_id: str = ""


# ``TurnCommitted.extra`` 的记忆标记。``SKIP_POST_MEMORY_KEY`` 为真时记忆引擎不从本回合
# 抽取记忆；``NOT_USER_AUTHORED_KEY`` 为真说明跳过的原因是本回合不是用户本人发言
# （群友、陌生人），这类回合仍会触发记忆整理，由整理按发送者拆段。
SKIP_POST_MEMORY_KEY = "skip_post_memory"
NOT_USER_AUTHORED_KEY = "not_user_authored"


@dataclass(frozen=True)
class TurnFailed:
    """A passive turn failed before any reply was committed.

    `error_summary` is user-safe: exception type plus one scrubbed line (see
    `shiori_sdk.errors`), never a traceback.
    """

    session_key: str
    error_summary: str


@dataclass(frozen=True)
class ProactiveMessageCommitted:
    """Signals that a proactive role message is available in its shared session.

    ``thread_id`` 是这条消息所在的会话；角色共享会话混存各会话的消息，订阅者
    读取历史时按它判定上下文归属。非角色共享会话没有会话划分，传空串。

    ``message_id`` names the committed message, so listeners publish exactly it
    instead of guessing from the session tail.
    """

    session_key: str
    channel: str
    role_id: str
    thread_id: str
    chat_id: str = ""
    assistant_response: str = ""
    tools_used: tuple[str, ...] = ()
    message_id: str = ""


@dataclass(frozen=True)
class ExternalImagePushed:
    """Describes one image successfully delivered through an external channel."""

    session_key: str
    role_id: str
    channel: str
    chat_id: str
    image: str
    attach_to_turn: bool = False
    already_persisted: bool = False


@dataclass(frozen=True)
class ExternalTextPushed:
    """One text delivered through an external channel by a model tool.

    ``in_turn`` marks a push the model made during a turn: it is committed
    with that turn. Otherwise a host-owned send (e.g. a scheduled job) is
    stored at once. Already-persisted and still-pending deliveries never
    raise it. ``delivery_key`` (host sends) and ``external_message_id`` (the
    platform's ID, when the sender reported one) identify the delivery, so it
    is stored once.

    ``tool`` names the sending tool (``message_push`` or ``account_send``);
    ``media`` are images sent with the text as the same message; and
    ``message_metadata`` is stored with the recorded message over the push
    defaults (e.g. the chat type and the account delivery facts: attempt,
    account, target and the ``ViaAccount`` snapshot).
    """

    session_key: str
    role_id: str
    channel: str
    chat_id: str
    text: str
    delivery_key: str = ""
    in_turn: bool = False
    external_message_id: str = ""
    tool: str = "message_push"
    media: tuple[str, ...] = ()
    message_metadata: dict[str, Any] = field(default_factory=_empty_metadata)
