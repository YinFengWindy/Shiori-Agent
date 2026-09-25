from __future__ import annotations

import pytest

from core.common.channel_chat_types import (
    ChatType,
    ChatTypeDeclaration,
    chat_id_command_reply,
    is_chat_id_command,
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
    chat_id: str, chat_type: ChatType, declarations: tuple[ChatTypeDeclaration, ...]
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
    chat_id: str, chat_type: ChatType, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        validate_chat_id_for_type(chat_id, chat_type, _QQ)


@pytest.mark.parametrize(
    "chat_id, chat_type",
    [
        # A pasted internal ID composes into a doubled prefix the transport misreads.
        ("gqq:gqq:831907794", "group"),
        ("gqq: gqq:831907794", "group"),
    ],
)
def test_rejects_a_prefix_written_twice(chat_id: str, chat_type: ChatType) -> None:
    with pytest.raises(ValueError, match="前缀只写一次"):
        validate_chat_id_for_type(chat_id, chat_type, _QQ)


def test_rejects_another_types_prefix_after_the_selected_one() -> None:
    declarations = (
        ChatTypeDeclaration("private", "私聊", "用户 ID", prefix="dm:"),
        ChatTypeDeclaration("group", "群聊", "群号", prefix="room:"),
    )

    with pytest.raises(ValueError, match="dm:<用户 ID>"):
        validate_chat_id_for_type("dm:room:1", "private", declarations)


@pytest.mark.parametrize(
    "text",
    ["/chatid", " /chatid ", "/CHATID", "/chatid@shiori_bot", "/myid", "/chatid x"],
)
def test_chat_id_command_is_recognized(text: str) -> None:
    assert is_chat_id_command(text)


@pytest.mark.parametrize("text", ["", "chatid", "/stop", "/chatids", "hi /chatid"])
def test_other_text_is_not_the_chat_id_command(text: str) -> None:
    assert not is_chat_id_command(text)


def test_chat_id_reply_gives_the_binding_form_fields_without_the_prefix() -> None:
    assert (
        chat_id_command_reply("gqq:831907794", "group", _QQ)
        == "会话类型：群聊\n群号：831907794"
    )
    assert chat_id_command_reply("3174898512", "private", _QQ) == (
        "会话类型：私聊\nQQ 号：3174898512"
    )
    assert chat_id_command_reply("-100", "group", _TELEGRAM) == (
        "会话类型：群聊\n群组 ID：-100"
    )


def test_chat_id_reply_requires_a_declared_type() -> None:
    with pytest.raises(ValueError, match="未声明会话类型 group"):
        chat_id_command_reply("x", "group", (_QQ[0],))
