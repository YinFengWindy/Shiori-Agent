"""Inbound events: fast ack, dedupe, message types, quotes, /stop, bindings."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from plugins.feishu.backend.inbound import parse_receive_event

CHAT_ID = "oc_chat"
OPEN_ID = "ou_user"


def test_parse_receive_event_reads_ids_and_content(make_event: Any) -> None:
    message = parse_receive_event(make_event(parent_id="om_parent"))

    assert message is not None
    assert (message.event_id, message.message_id, message.chat_id) == (
        "ev_1",
        "om_in_1",
        CHAT_ID,
    )
    assert (message.chat_type, message.sender_open_id) == ("p2p", OPEN_ID)
    assert message.content == {"text": "你好"}
    assert message.parent_id == "om_parent"
    assert parse_receive_event({"event": {"message": {}}}) is None


async def test_text_message_is_routed_to_the_bound_role(
    harness: Any, make_event: Any
) -> None:
    connection = await harness.start()

    connection.emit(make_event())
    await harness.settle()

    [inbound] = harness.bus.inbound
    assert (inbound.channel, inbound.chat_id, inbound.sender) == (
        "feishu",
        CHAT_ID,
        OPEN_ID,
    )
    assert inbound.content == "你好"
    assert inbound.metadata["chat_type"] == "private"
    assert inbound.metadata["external_message_id"] == "om_in_1"
    assert inbound.metadata["role_id"] == "mira"


async def test_handler_acks_before_slow_processing_finishes(
    harness: Any, make_event: Any
) -> None:
    connection = await harness.start()
    harness.api.gate = asyncio.Event()  # holds the image download open

    elapsed = connection.emit(
        make_event(message_type="image", content={"image_key": "img_x"})
    )

    # The SDK acks right after the handler returns; it must not wait for
    # downloads or the turn, which here cannot finish until the gate opens.
    assert elapsed < 0.5
    await asyncio.sleep(0.05)
    assert harness.bus.inbound == []
    harness.api.gate.set()
    await harness.settle()
    assert [item.content for item in harness.bus.inbound] == ["[图片]"]


async def test_redelivered_events_are_processed_once(
    harness: Any, make_event: Any
) -> None:
    connection = await harness.start()

    connection.emit(make_event(event_id="ev_1", message_id="om_1"))
    connection.emit(make_event(event_id="ev_1", message_id="om_1"))
    connection.emit(make_event(event_id="ev_2", message_id="om_1"))
    await harness.settle()

    assert len(harness.bus.inbound) == 1


async def test_group_messages_are_ignored(harness: Any, make_event: Any) -> None:
    connection = await harness.start()

    connection.emit(make_event(chat_type="group"))
    await harness.settle()

    assert harness.bus.inbound == []


async def test_image_file_and_post_attachments_are_downloaded(
    harness: Any, make_event: Any
) -> None:
    connection = await harness.start()

    connection.emit(
        make_event(
            message_id="m1",
            event_id="e1",
            message_type="image",
            content={"image_key": "img_1"},
        )
    )
    connection.emit(
        make_event(
            message_id="m2",
            event_id="e2",
            message_type="file",
            content={"file_key": "f_1", "file_name": "报告.pdf"},
        )
    )
    connection.emit(
        make_event(
            message_id="m3",
            event_id="e3",
            message_type="post",
            content={
                "title": "",
                "content": [
                    [{"tag": "text", "text": "看图"}],
                    [{"tag": "img", "image_key": "img_2"}],
                ],
            },
        )
    )
    await harness.settle()

    image, document, post = harness.bus.inbound
    assert image.content == "[图片]" and Path(image.media[0]).suffix == ".png"
    assert document.content == "[文件: 报告.pdf]"
    assert Path(document.media[0]).suffix == ".pdf"
    assert post.content == "看图" and len(post.media) == 1
    assert all(
        Path(path).read_bytes().startswith(b"\x89PNG")
        for item in (image, document, post)
        for path in item.media
    )
    downloads = [path for method, path, _ in harness.api.calls if "/resources/" in path]
    assert downloads == [
        "/open-apis/im/v1/messages/m1/resources/img_1",
        "/open-apis/im/v1/messages/m2/resources/f_1",
        "/open-apis/im/v1/messages/m3/resources/img_2",
    ]


async def test_quoting_a_bot_card_merges_its_text_into_the_turn(
    harness: Any, make_event: Any
) -> None:
    harness.api.messages["om_bot"] = {
        "msg_type": "interactive",
        "sender": {"sender_type": "app"},
        "body": {
            "content": json.dumps({"elements": [[{"tag": "text", "text": "明天有雨"}]]})
        },
    }
    connection = await harness.start()

    connection.emit(make_event(content={"text": "要带伞吗"}, parent_id="om_bot"))
    await harness.settle()

    [inbound] = harness.bus.inbound
    assert "明天有雨" in inbound.content and "要带伞吗" in inbound.content
    assert "你（机器人）" in inbound.content
    assert inbound.metadata["reply_to_message_id"] == "om_bot"


async def test_quoting_a_user_image_attaches_it(harness: Any, make_event: Any) -> None:
    harness.api.messages["om_img"] = {
        "msg_type": "image",
        "sender": {"sender_type": "user"},
        "body": {"content": json.dumps({"image_key": "img_old"})},
    }
    connection = await harness.start()

    connection.emit(make_event(content={"text": "这是什么"}, parent_id="om_img"))
    await harness.settle()

    [inbound] = harness.bus.inbound
    assert "[图片]" in inbound.content and len(inbound.media) == 1


async def test_stop_command_interrupts_the_bound_role_session(
    harness: Any, make_event: Any
) -> None:
    connection = await harness.start()

    connection.emit(make_event(content={"text": "/stop"}))
    await harness.settle()

    assert harness.bus.inbound == []
    assert harness.interrupts.requests == [
        {"session_key": "role:mira", "sender": OPEN_ID, "command": "/stop"}
    ]
    assert harness.api.sent_texts() == ["已停止当前回复。"]


async def test_unbound_sender_is_rejected_and_shown_in_status(
    make_harness: Any, make_event: Any
) -> None:
    harness = make_harness(allowed=False)
    connection = await harness.start()

    connection.emit(make_event())
    connection.emit(
        make_event(event_id="ev_s", message_id="om_s", content={"text": "/stop"})
    )
    await harness.settle()

    assert harness.bus.inbound == []
    assert harness.interrupts.requests == []
    detail = harness.channel.status()["detail"]
    assert f"chat_id={CHAT_ID}" in detail and f"open_id={OPEN_ID}" in detail


async def test_allow_from_filters_before_any_download(
    make_harness: Any, make_event: Any
) -> None:
    harness = make_harness(allow_from=["ou_someone_else"])
    connection = await harness.start()

    connection.emit(make_event(message_type="image", content={"image_key": "i"}))
    await harness.settle()

    assert harness.bus.inbound == []
    assert not any("/resources/" in path for _m, path, _b in harness.api.calls)


async def test_paused_intake_buffers_until_resumed(
    harness: Any, make_event: Any
) -> None:
    connection = await harness.start()
    harness.channel.pause_intake()

    connection.emit(make_event())
    await harness.settle()
    assert harness.bus.inbound == []

    harness.channel.resume_intake()
    await harness.settle()
    assert [item.content for item in harness.bus.inbound] == ["你好"]
