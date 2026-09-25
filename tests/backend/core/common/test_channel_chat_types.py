from __future__ import annotations

import pytest

from core.common.channel_chat_types import (
    ChatTypeDeclaration,
    validate_chat_id_for_type,
)

_QQ = (
    ChatTypeDeclaration("private", "私聊", "QQ 号"),
    ChatTypeDeclaration("group", "群聊", "群号", prefix="gqq:"),
)
_TELEGRAM = (
    ChatTypeDeclaration("private", "私聊", "用户 ID"),
    ChatTypeDeclaration("group", "群聊", "群组 ID"),
)


@pytest.mark.parametrize(
    "chat_id, chat_type, declarations",
    [
        ("3174898512", "private", _QQ),
        ("gqq:831907794", "group", _QQ),
        # Without prefixes the type cannot be checked against the ID.
        ("-1001", "private", _TELEGRAM),
        ("42", "group", _TELEGRAM),
    ],
)
def test_accepts_chat_id_matching_the_declared_type(
    chat_id: str, chat_type: str, declarations: tuple[ChatTypeDeclaration, ...]
) -> None:
    validate_chat_id_for_type(chat_id, chat_type, declarations)


@pytest.mark.parametrize(
    "chat_id, chat_type, message",
    [
        ("831907794", "group", "群聊会话 ID 必须是 gqq:<群号>"),
        ("gqq: ", "group", "gqq:<群号>"),
        ("gqq:831907794", "private", "群聊格式，与所选的私聊不符"),
        ("831907794", "channel", "可选：私聊、群聊"),
    ],
)
def test_rejects_chat_id_inconsistent_with_the_declared_type(
    chat_id: str, chat_type: str, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        validate_chat_id_for_type(chat_id, chat_type, _QQ)
