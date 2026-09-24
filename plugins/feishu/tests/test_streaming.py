"""End-to-end CardKit live reply: host stream gate, coalescing, final frame.

Only the network is faked; the channel, the host ``ChannelDirectory`` and the
agent loop's stream sink are the real ones.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from agent.looping.core import AgentLoop
from bus.events import InboundMessage, OutboundMessage
from bus.events_lifecycle import TurnStarted
from core.common.channel_directory import ChannelDirectory
from plugins.feishu.backend.formatting import CARD_TEXT_LIMIT, LIVE_ELEMENT_ID

SESSION_KEY = "role:mira"
CHAT_ID = "oc_chat"


async def _turn(harness: Any, make_event: Any) -> Any:
    """Starts the channel, receives one message and opens its turn."""
    connection = await harness.start()
    connection.emit(make_event())
    await harness.settle()
    [inbound] = harness.bus.inbound
    await harness.event_bus.observe(
        TurnStarted(
            session_key=SESSION_KEY,
            channel="feishu",
            chat_id=CHAT_ID,
            content=inbound.content,
            # The agent loop reports the inbound message's own timestamp.
            timestamp=inbound.timestamp,
        )
    )
    return _stream_sink(harness.channel, harness.event_bus, inbound)


def _stream_sink(channel: Any, event_bus: Any, inbound: InboundMessage) -> Any:
    loop = object.__new__(AgentLoop)
    loop._event_bus = event_bus
    loop._active_turn_states = {}
    directory = ChannelDirectory()
    directory.bind({"feishu": channel}.get)
    loop._channel_directory = directory
    sink = AgentLoop._build_stream_event_sink(loop, inbound)
    assert sink is not None
    return sink


def _final(content: str) -> OutboundMessage:
    return OutboundMessage(
        channel="feishu",
        chat_id=CHAT_ID,
        content=content,
        metadata={"role_id": "mira", "session_key_override": SESSION_KEY},
    )


def _stream_updates(api: Any) -> list[tuple[str, int]]:
    return [(body["content"], body["sequence"]) for body in api.bodies("stream_text")]


def test_hooks_opt_private_chats_into_streaming_and_rendering_rules(
    harness: Any,
) -> None:
    directory = ChannelDirectory()
    directory.bind({"feishu": harness.channel}.get)

    assert directory.supports_stream_events("feishu", CHAT_ID)
    hint = directory.system_prompt_hint("feishu", CHAT_ID)
    assert hint.startswith("## 飞书渠道渲染限制")
    assert "`channel=feishu`" in hint
    assert directory.default_chat_type("feishu") == "private"


async def test_deltas_coalesce_into_one_card_finished_in_place(
    harness: Any, make_event: Any
) -> None:
    harness.channel._streamer._min_interval = 0.01
    sink = await _turn(harness, make_event)

    await sink("今天")
    await sink("晴，")  # arrives while the first refresh is pending
    await harness.channel._streamer.drain()
    await sink("最高 25 度")
    await harness.channel._streamer.drain()
    await harness.channel._on_response(_final("今天晴，最高 25 度。"))

    api = harness.api
    assert len(api.bodies("create_card")) == 1
    card = json.loads(api.bodies("create_card")[0]["data"])
    assert card["config"]["streaming_mode"] is True
    # The live card answers the user's message as a quoting reply.
    assert api.bodies("send") == []
    [(_method, path, sent)] = [c for c in api.calls if c[1].endswith("/reply")]
    assert path == "/open-apis/im/v1/messages/om_in_1/reply"
    assert json.loads(sent["content"])["data"]["card_id"].startswith("card_")
    assert _stream_updates(api) == [
        ("今天晴，", 1),
        ("今天晴，最高 25 度", 2),
        ("今天晴，最高 25 度。", 3),
    ]
    [closing] = api.bodies("card_settings")
    assert closing["sequence"] == 4
    assert json.loads(closing["settings"])["config"]["streaming_mode"] is False
    assert api.sent_texts() == []  # no second copy of the reply
    assert all(
        path.split("/")[-2] == LIVE_ELEMENT_ID
        for m, path, _b in api.calls
        if path.endswith("/content")
    )
    assert harness.hub.deliveries == ["sent"]


async def test_a_long_final_reply_continues_in_follow_up_cards(
    harness: Any, make_event: Any
) -> None:
    harness.channel._streamer._min_interval = 0.01
    sink = await _turn(harness, make_event)
    await sink("开头")
    await harness.channel._streamer.drain()
    final = "甲" * (CARD_TEXT_LIMIT - 10) + "\n" + "乙" * 20

    await harness.channel._on_response(_final(final))

    assert _stream_updates(harness.api)[-1][0] == "甲" * (CARD_TEXT_LIMIT - 10) + "\n"
    assert harness.api.sent_texts() == ["乙" * 20]
    # Only the live card quotes the user; the follow-up part does not.
    assert harness.api.keys().count("reply") == 1
    assert harness.api.keys()[-1] == "send"


async def test_card_creation_failure_falls_back_to_a_normal_message(
    harness: Any, make_event: Any
) -> None:
    harness.api.fail("create_card", (400, 99991672))  # e.g. missing cardkit scope
    sink = await _turn(harness, make_event)

    await sink("半句")
    await harness.channel._streamer.drain()
    await sink("话")  # the live card is disabled for this turn
    await harness.channel._streamer.drain()
    await harness.channel._on_response(_final("半句话。"))

    assert len(harness.api.bodies("create_card")) == 1
    assert harness.api.bodies("stream_text") == []
    assert harness.api.sent_texts() == ["半句话。"]
    assert harness.hub.deliveries == ["sent"]


async def test_a_failed_final_frame_recalls_the_card_before_the_fallback(
    harness: Any, make_event: Any
) -> None:
    sink = await _turn(harness, make_event)
    await sink("预览")
    await harness.channel._streamer.drain()
    harness.api.fail("stream_text", (400, 300317))

    await harness.channel._on_response(_final("最终回复"))

    keys = harness.api.keys()
    assert keys.index("delete") < len(keys) - 1
    assert keys[-1] == "send"
    assert harness.api.sent_texts() == ["最终回复"]


async def test_streaming_timeout_is_finished_with_a_full_card_update(
    harness: Any, make_event: Any
) -> None:
    sink = await _turn(harness, make_event)
    await sink("预览")
    await harness.channel._streamer.drain()
    harness.api.fail("stream_text", (400, 200850))  # streaming mode timed out

    await harness.channel._on_response(_final("最终回复"))

    [update] = harness.api.bodies("update_card")
    card = json.loads(update["card"]["data"])
    assert card["body"]["elements"][0]["content"] == "最终回复"
    assert "streaming_mode" not in card["config"]
    assert harness.api.sent_texts() == []


async def test_rate_limits_back_off_without_disabling_the_card(
    harness: Any, make_event: Any
) -> None:
    harness.channel._streamer._min_interval = 0.01
    sink = await _turn(harness, make_event)
    await sink("一")
    await harness.channel._streamer.drain()
    harness.api.fail("stream_text", (429, 99991400))

    await sink("二")
    await harness.channel._streamer.drain()

    [card] = harness.channel._streamer._cards.values()
    assert not card.disabled and card.shown == "一二"
    # The limited request is retried after backing off, with a new sequence.
    assert _stream_updates(harness.api) == [("一", 1), ("一二", 2), ("一二", 3)]


async def test_a_card_left_open_by_an_interrupted_turn_is_closed(
    harness: Any, make_event: Any
) -> None:
    sink = await _turn(harness, make_event)
    await sink("说到一半")
    await harness.channel._streamer.drain()

    # /stop: no outbound reply arrives; the next turn closes the old card.
    await harness.event_bus.observe(
        TurnStarted(
            session_key=SESSION_KEY,
            channel="feishu",
            chat_id=CHAT_ID,
            content="下一句",
            timestamp=datetime.now(),
        )
    )
    await harness.channel._streamer.drain()

    [closing] = harness.api.bodies("card_settings")
    assert json.loads(closing["settings"])["config"]["streaming_mode"] is False
    assert not harness.channel._streamer.has_card(SESSION_KEY)


async def test_stop_cancels_pending_refreshes(harness: Any, make_event: Any) -> None:
    harness.channel._streamer._min_interval = 60.0
    sink = await _turn(harness, make_event)
    await sink("一")
    await harness.channel._streamer.drain()
    await sink("二")  # waits for the 60 s interval

    await harness.channel.stop()

    assert harness.channel._streamer._tasks == {}
    assert [content for content, _seq in _stream_updates(harness.api)] == ["一"]


async def test_a_turn_without_an_inbound_message_streams_unquoted(
    harness: Any, make_event: Any
) -> None:
    await harness.start()
    await harness.event_bus.observe(
        TurnStarted(
            session_key=SESSION_KEY,
            channel="feishu",
            chat_id=CHAT_ID,
            content="定时任务",
            timestamp=datetime.now(),
        )
    )
    inbound = InboundMessage(
        channel="feishu", sender="ou_user", chat_id=CHAT_ID, content="定时任务"
    )
    sink = _stream_sink(harness.channel, harness.event_bus, inbound)

    await sink("提醒")
    await harness.channel._streamer.drain()
    await harness.channel._on_response(_final("提醒你喝水"))

    assert "reply" not in harness.api.keys()
    assert harness.api.keys()[:2] == ["create_card", "send"]
