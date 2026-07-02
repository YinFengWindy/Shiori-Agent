from __future__ import annotations
from typing import Any, cast

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent.core.passive_support import (
    build_post_reply_context_budget,
    estimate_history_budget,
)
from agent.core.passive_turn import DefaultContextStore, _format_group_context_lines
from agent.core.types import RetrievalTrace
from agent.retrieval.protocol import RetrievalResult
from bus.events import InboundMessage


class _DummySession:
    def __init__(self) -> None:
        self.key = "cli:1"
        self.metadata: dict[str, object] = {"mode": "test"}
        self.messages = [
            {
                "role": "user",
                "content": "hello",
                "tools_used": ["read_file"],
                "tool_chain": [
                    {
                        "text": "tool run",
                        "calls": [
                            {
                                "call_id": "call-1",
                                "name": "read_file",
                                "arguments": {"path": "/tmp/a.txt"},
                                "result": "ok",
                            }
                        ],
                    }
                ],
            },
            {"role": "assistant", "content": "world"},
        ]
        self.last_consolidated = 0

    def get_history(self, max_messages: int = 500) -> list[dict]:
        return self.messages[-max_messages:]


class _GroupContextSessionManager:
    def __init__(self) -> None:
        self.sessions = {
            "groupctx:qq:100": SimpleNamespace(
                key="groupctx:qq:100",
                messages=[
                    {
                        "role": "user",
                        "content": "B 先前说过的话",
                        "metadata": {"member_id": "2"},
                    },
                    {
                        "role": "assistant",
                        "content": "角色刚才在群里的回复",
                        "metadata": {"group_context": True},
                    },
                    {
                        "role": "user",
                        "content": "当前这条消息",
                        "metadata": {"member_id": "1"},
                    },
                ],
                metadata={},
            )
        }

    def get_or_create(self, key: str):
        return self.sessions.setdefault(key, SimpleNamespace(key=key, messages=[], metadata={}))


@pytest.mark.asyncio
async def test_default_context_store_prepare_returns_bundle_with_legacy_metadata():
    retrieval = SimpleNamespace(
        retrieve=AsyncMock(
            return_value=RetrievalResult(
                block="remembered",
                trace=RetrievalTrace(raw={"route": "RETRIEVE"}),
                metadata={"source": "memory2"},
            )
        )
    )
    context = SimpleNamespace(
        skills=SimpleNamespace(
            list_skills=MagicMock(
                return_value=[{"name": "refactor"}, {"name": "known"}]
            )
        )
    )
    store = DefaultContextStore(
        retrieval=cast(Any, retrieval),
        context=cast(Any, context),
    )
    session = _DummySession()
    msg = InboundMessage(
        channel="cli",
        sender="hua",
        chat_id="1",
        content="请用 $refactor 再来一次 $known $refactor",
        timestamp=datetime(2026, 4, 4, 20, 0, 0),
    )

    bundle = await store.prepare(msg=msg, session_key="cli:1", session=cast(Any, session))

    assert [item.content for item in bundle.history] == ["hello", "world"]
    assert bundle.memory_blocks == ["remembered"]
    assert bundle.skill_mentions == ["refactor", "known"]
    assert bundle.retrieved_memory_block == "remembered"
    assert bundle.retrieval_trace_raw == {"route": "RETRIEVE"}
    assert bundle.retrieval_metadata == {"source": "memory2"}
    assert bundle.history_messages[0].tool_chain[0].calls[0].name == "read_file"
    assert bundle.metadata == {}
    request = retrieval.retrieve.await_args.args[0]
    assert request.session_key == "cli:1"
    assert request.history[0].tools_used == ["read_file"]


@pytest.mark.asyncio
async def test_default_context_store_prepare_uses_explicit_session_key_for_retrieval():
    retrieval = SimpleNamespace(
        retrieve=AsyncMock(
            return_value=RetrievalResult(
                block="remembered",
                trace=RetrievalTrace(raw={"route": "RETRIEVE"}),
            )
        )
    )
    context = SimpleNamespace(
        skills=SimpleNamespace(list_skills=MagicMock(return_value=[]))
    )
    store = DefaultContextStore(retrieval=cast(Any, retrieval), context=cast(Any, context))
    session = _DummySession()
    msg = InboundMessage(
        channel="telegram",
        sender="hua",
        chat_id="7674283004",
        content="定时任务执行一下",
    )

    await store.prepare(msg=msg, session_key="scheduler:job-123", session=cast(Any, session))

    request = retrieval.retrieve.await_args.args[0]
    assert request.session_key == "scheduler:job-123"
    assert request.session_key != msg.session_key


@pytest.mark.asyncio
async def test_default_context_store_prepare_skips_retrieval_when_requested():
    retrieval = SimpleNamespace(
        retrieve=AsyncMock(
            return_value=RetrievalResult(
                block="should-not-load",
                trace=RetrievalTrace(raw={"route": "RETRIEVE"}),
            )
        )
    )
    context = SimpleNamespace(
        skills=SimpleNamespace(list_skills=MagicMock(return_value=[]))
    )
    store = DefaultContextStore(retrieval=cast(Any, retrieval), context=cast(Any, context))
    session = _DummySession()
    msg = InboundMessage(
        channel="telegram",
        sender="scheduler",
        chat_id="7674283004",
        content="查询北京天气",
        metadata={"skip_memory_retrieval": True},
    )

    bundle = await store.prepare(
        msg=msg,
        session_key="scheduler:job-123",
        session=cast(Any, session),
    )

    retrieval.retrieve.assert_not_awaited()
    assert bundle.memory_blocks == []
    assert bundle.retrieved_memory_block == ""
    assert bundle.retrieval_trace_raw is None


@pytest.mark.asyncio
async def test_default_context_store_uses_cli_context_override_for_retrieval():
    retrieval = SimpleNamespace(
        retrieve=AsyncMock(
            return_value=RetrievalResult(
                block="remembered",
                trace=RetrievalTrace(raw={"route": "RETRIEVE"}),
            )
        )
    )
    context = SimpleNamespace(
        skills=SimpleNamespace(list_skills=MagicMock(return_value=[]))
    )
    store = DefaultContextStore(retrieval=cast(Any, retrieval), context=cast(Any, context))
    session = _DummySession()
    msg = InboundMessage(
        channel="cli",
        sender="hua",
        chat_id="local",
        content="测试",
        metadata={
            "session_key_override": "telegram:7674283004",
            "context_channel": "telegram",
            "context_chat_id": "7674283004",
        },
    )

    await store.prepare(msg=msg, session_key=msg.session_key, session=cast(Any, session))

    request = retrieval.retrieve.await_args.args[0]
    assert request.session_key == "telegram:7674283004"
    assert request.channel == "telegram"
    assert request.chat_id == "7674283004"


@pytest.mark.asyncio
async def test_default_context_store_injects_group_shared_background_without_repeating_current_message():
    retrieval = SimpleNamespace(
        retrieve=AsyncMock(
            return_value=RetrievalResult(
                block="remembered",
                trace=RetrievalTrace(raw={"route": "RETRIEVE"}),
            )
        )
    )
    context = SimpleNamespace(
        skills=SimpleNamespace(list_skills=MagicMock(return_value=[]))
    )
    store = DefaultContextStore(
        retrieval=cast(Any, retrieval),
        context=cast(Any, context),
        session_manager=cast(Any, _GroupContextSessionManager()),
    )
    session = _DummySession()
    session.metadata.update(
        {
            "role_id": "mira",
            "is_group_chat": True,
            "group_id": "100",
            "group_member_id": "1",
        }
    )
    msg = InboundMessage(
        channel="qq",
        sender="1",
        chat_id="gqq:100",
        content="当前这条消息",
        metadata={
            "role_id": "mira",
            "is_group_chat": True,
            "group_id": "100",
            "group_member_id": "1",
            "member_name": "花月",
            "group_context_key": "groupctx:qq:100",
        },
    )

    bundle = await store.prepare(msg=msg, session_key="role:mira:group:100:member:1", session=cast(Any, session))

    assert "remembered" in bundle.retrieved_memory_block
    assert "## 当前群成员" in bundle.retrieved_memory_block
    assert "名称: 花月" in bundle.retrieved_memory_block
    assert "## 群聊共享背景" in bundle.retrieved_memory_block
    assert "[2] B 先前说过的话" in bundle.retrieved_memory_block
    assert "[角色] 角色刚才在群里的回复" in bundle.retrieved_memory_block
    assert "当前这条消息" not in bundle.retrieved_memory_block


def test_format_group_context_lines_filters_low_signal_and_prioritizes_current_member():
    lines = _format_group_context_lines(
        [
            {
                "role": "user",
                "content": "路人早些时候的背景",
                "metadata": {"member_id": "9"},
            },
            {
                "role": "user",
                "content": "我刚才说想继续看支付记录",
                "metadata": {"member_id": "1"},
            },
            {
                "role": "user",
                "content": "[图片]",
                "metadata": {"member_id": "2"},
            },
            {
                "role": "user",
                "content": "哈哈",
                "metadata": {"member_id": "3"},
            },
            {
                "role": "user",
                "content": "其他成员补充了支付背景",
                "metadata": {"member_id": "2"},
            },
            {
                "role": "assistant",
                "content": "角色刚才提醒先核对账单",
                "metadata": {"group_context": True},
            },
            {
                "role": "user",
                "content": "当前这条消息",
                "metadata": {"member_id": "1"},
            },
        ],
        current_message="当前这条消息",
        current_member_id="1",
        limit=3,
    )

    assert lines == [
        "- [1] 我刚才说想继续看支付记录",
        "- [2] 其他成员补充了支付背景",
        "- [角色] 角色刚才提醒先核对账单",
    ]


def test_estimate_history_budget_returns_serialized_history_size():
    stats = estimate_history_budget(
        [
            {"role": "user", "content": "你好"},
            {
                "role": "assistant",
                "content": "收到",
                "tool_calls": [{"id": "call-1", "name": "read_file"}],
            },
        ]
    )

    assert stats["messages"] == 2
    assert stats["chars"] > 0
    assert stats["tokens"] == max(1, stats["chars"] // 3)


def test_build_post_reply_context_budget_combines_history_and_prompt():
    context = SimpleNamespace(
        last_debug_breakdown=[
            SimpleNamespace(est_tokens=100),
            SimpleNamespace(est_tokens=250),
        ]
    )

    budget = build_post_reply_context_budget(
        context=cast(Any, context),
        history=[{"role": "user", "content": "你好"}],
        history_window=40,
    )

    assert budget["history_window"] == 40
    assert budget["history_messages"] == 1
    assert budget["history_chars"] > 0
    assert budget["history_tokens"] == max(1, budget["history_chars"] // 3)
    assert budget["prompt_tokens"] == 350
    assert budget["next_turn_baseline_tokens"] == (
        budget["history_tokens"] + 350
    )
