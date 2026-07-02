"""Tests for current proactive.memory_optimizer behavior."""

from typing import Any, cast
import asyncio
import types
from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from core.roles import RoleStore
from proactive_v2.memory_optimizer import (
    MemoryOptimizerBusy,
    MemoryOptimizer,
    MemoryOptimizerLoop,
)
from core.memory.markdown import MarkdownMemoryStore


class _Resp:
    def __init__(self, content: str) -> None:
        self.content = content


def _provider_with_responses(*responses: str) -> object:
    provider = types.SimpleNamespace()
    provider.chat = AsyncMock(side_effect=[_Resp(x) for x in responses])
    return provider


def test_optimize_skips_when_memory_pending_history_all_empty(tmp_path):
    memory = MarkdownMemoryStore(tmp_path)
    provider = types.SimpleNamespace()
    provider.chat = AsyncMock()

    optimizer = MemoryOptimizer(memory, cast(Any, provider), "test-model", tmp_path)
    optimizer._STEP_DELAY_SECONDS = 0
    with pytest.raises(ValueError, match="role_id required for memory optimizer"):
        asyncio.run(optimizer.optimize())

    provider.chat.assert_not_called()


def test_optimize_rewrites_memory_from_first_llm_call(tmp_path):
    memory = MarkdownMemoryStore(tmp_path)
    role_memory = MarkdownMemoryStore(tmp_path / "roles" / "mira")
    role_memory.write_long_term("old profile")

    provider = _provider_with_responses("## 用户画像\n- 新版本\n")
    optimizer = MemoryOptimizer(memory, cast(Any, provider), "test-model", tmp_path)
    optimizer._STEP_DELAY_SECONDS = 0
    asyncio.run(optimizer.optimize(role_id="mira"))

    assert role_memory.read_long_term().strip() == "## 用户画像\n- 新版本"


def test_optimize_rolls_back_snapshot_when_merge_returns_empty(tmp_path):
    memory = MarkdownMemoryStore(tmp_path)
    role_memory = MarkdownMemoryStore(tmp_path / "roles" / "mira")
    role_memory.write_long_term("old profile")
    role_memory.append_pending("- pending fact")

    provider = _provider_with_responses("")
    optimizer = MemoryOptimizer(memory, cast(Any, provider), "test-model", tmp_path)
    optimizer._STEP_DELAY_SECONDS = 0
    asyncio.run(optimizer.optimize(role_id="mira"))

    assert "pending fact" in role_memory.read_pending()
    assert not role_memory._snapshot_path.exists()


def test_optimize_updates_self_using_pending_only(tmp_path):
    memory = MarkdownMemoryStore(tmp_path)
    role_memory = MarkdownMemoryStore(tmp_path / "roles" / "mira")
    role_memory.write_long_term("old")
    role_memory.write_self("## 原 SELF")
    role_memory.append_pending("- [preference] 回复保持简洁。")
    role_memory.append_history("[2026-03-03 10:00] USER: 这段历史不该进入 SELF")

    provider = _provider_with_responses(
        "## 新记忆",
        "# 角色自我认知\n\n## 人格与形象\n\n- 新版人格\n\n## 我对当前用户的理解\n\n- 新版理解\n\n## 我们关系的定义\n\n- 新版关系\n",
    )
    optimizer = MemoryOptimizer(memory, cast(Any, provider), "test-model", tmp_path)
    optimizer._STEP_DELAY_SECONDS = 0
    asyncio.run(optimizer.optimize(role_id="mira"))

    assert role_memory.read_self().strip().startswith("# 角色自我认知")
    assert "新版理解" in role_memory.read_self()

    self_prompt = provider.chat.await_args_list[1].kwargs["messages"][1]["content"]
    assert "- [preference] 回复保持简洁。" in self_prompt
    assert "这段历史不该进入 SELF" not in self_prompt


def test_merge_memory_ignores_history_and_only_uses_pending(tmp_path):
    memory = MarkdownMemoryStore(tmp_path)
    role_memory = MarkdownMemoryStore(tmp_path / "roles" / "mira")
    role_memory.write_long_term("old profile")
    role_memory.append_pending("- [identity] 新身份")
    role_memory.append_history("[2026-03-03 10:00] USER: 这段历史不该进入长期记忆")

    provider = _provider_with_responses("## 用户画像\n- 新版本\n")
    optimizer = MemoryOptimizer(memory, cast(Any, provider), "test-model", tmp_path)
    optimizer._STEP_DELAY_SECONDS = 0
    asyncio.run(optimizer.optimize(role_id="mira"))

    call = provider.chat.await_args_list[0]
    prompt = call.kwargs["messages"][1]["content"]

    assert "近期历史摘要" not in prompt
    assert "- [identity] 新身份" in prompt


def test_update_self_does_not_copy_user_preference_facts_verbatim(tmp_path):
    memory = MarkdownMemoryStore(tmp_path)
    role_memory = MarkdownMemoryStore(tmp_path / "roles" / "mira")
    role_memory.write_self("# 角色自我认知\n\n## 人格与形象\n- 旧人格\n\n## 我对当前用户的理解\n- 旧理解\n\n## 我们关系的定义\n- 旧关系\n")

    provider = _provider_with_responses(
        "# 角色自我认知\n\n## 人格与形象\n- 角色依旧保持自己的审美与语气\n\n## 我对当前用户的理解\n- 我知道用户对视觉表达有稳定要求，但不会把具体偏好清单写进自我认知\n\n## 我们关系的定义\n- 我会根据这些长期信号调整相处方式\n",
    )
    optimizer = MemoryOptimizer(memory, cast(Any, provider), "test-model", tmp_path)
    optimizer._STEP_DELAY_SECONDS = 0

    asyncio.run(
        optimizer._update_self(
            role_memory,
            "- [preference] 用户偏好rurudo画风（柔光透亮质感）",
        )
    )

    updated = role_memory.read_self()
    assert "用户偏好rurudo画风" not in updated
    assert "具体偏好清单" in updated


def test_request_text_response_uses_expected_chat_kwargs(tmp_path):
    memory = MarkdownMemoryStore(tmp_path)
    provider = _provider_with_responses("merged")
    optimizer = MemoryOptimizer(memory, cast(Any, provider), "test-model", tmp_path)

    result = asyncio.run(
        optimizer._request_text_response(
            system_content="system",
            user_content="user",
            max_tokens=123,
        )
    )

    assert result == "merged"
    kwargs = provider.chat.await_args.kwargs
    assert kwargs["tools"] == []
    assert kwargs["model"] == "test-model"
    assert kwargs["max_tokens"] == 123


def test_optimize_reports_busy_instead_of_waiting(tmp_path):
    async def run_case() -> None:
        memory = MarkdownMemoryStore(tmp_path)
        provider = types.SimpleNamespace()
        provider.chat = AsyncMock()
        optimizer = MemoryOptimizer(memory, cast(Any, provider), "test-model", tmp_path)
        started = asyncio.Event()
        release = asyncio.Event()

        async def blocked_optimize(*, role_id: str | None = None) -> None:
            started.set()
            await release.wait()

        optimizer._optimize = blocked_optimize  # type: ignore[method-assign]
        running = asyncio.create_task(optimizer.optimize(role_id="mira"))
        await started.wait()

        assert optimizer.is_running
        with pytest.raises(MemoryOptimizerBusy):
            await optimizer.optimize(role_id="mira")

        release.set()
        await running

    asyncio.run(run_case())


def test_optimize_with_role_id_updates_role_markdown_memory(tmp_path):
    _ = RoleStore(tmp_path).create_role(
        role_id="mira",
        name="Mira",
        description="",
        system_prompt="you are mira",
    )
    global_memory = MarkdownMemoryStore(tmp_path)
    role_memory = MarkdownMemoryStore(tmp_path / "roles" / "mira")
    role_memory.write_long_term("角色旧记忆")
    role_memory.write_self("## 旧 SELF")
    role_memory.append_pending("- [identity] 角色新事实")
    global_memory.write_long_term("全局旧记忆")

    provider = _provider_with_responses(
        "## 用户画像\n- 角色新版本\n",
        "# 角色自我认知\n\n## 人格与形象\n\n- 角色人格\n\n## 我对当前用户的理解\n\n- 角色理解\n\n## 我们关系的定义\n\n- 角色关系\n",
    )
    optimizer = MemoryOptimizer(
        global_memory,
        cast(Any, provider),
        "test-model",
        tmp_path,
    )
    optimizer._STEP_DELAY_SECONDS = 0

    asyncio.run(optimizer.optimize(role_id="mira"))

    assert "角色新版本" in role_memory.read_long_term()
    assert "角色理解" in role_memory.read_self()
    assert "全局旧记忆" in global_memory.read_long_term()
    role = RoleStore(tmp_path).get_role("mira")
    assert role is not None
    assert role.memory_init_state.get("last_memory_optimized_at")


def test_optimize_updates_member_memory_from_member_pending(tmp_path):
    _ = RoleStore(tmp_path).create_role(
        role_id="mira",
        name="Mira",
        description="",
        system_prompt="you are mira",
    )
    global_memory = MarkdownMemoryStore(tmp_path)
    role_memory = MarkdownMemoryStore(tmp_path / "roles" / "mira")
    role_memory.write_member_memory("# Member Memory\n\n## qq:old\n- 关系: 老成员\n")
    assert role_memory.append_member_pending_entry(
        member_key="qq:3174898512",
        source_ref='["msg-1"]',
        history_entry_payloads=[("[2026-07-02 15:00] 用户频繁纠正我别话密。", 6)],
        pending_items="- [preference] 用户偏好短、脆、别乱猜。",
    )

    provider = _provider_with_responses(
        "# Member Memory\n\n## qq:old\n- 关系: 老成员\n\n## qq:3174898512\n- 关系: 互动频繁，常直接纠正我。\n- 偏好: 喜欢短、脆、别乱猜的回复。\n"
    )
    optimizer = MemoryOptimizer(
        global_memory,
        cast(Any, provider),
        "test-model",
        tmp_path,
    )
    optimizer._STEP_DELAY_SECONDS = 0

    asyncio.run(optimizer.optimize(role_id="mira"))

    updated = role_memory.read_member_memory()
    assert "## qq:3174898512" in updated
    assert "喜欢短、脆、别乱猜的回复" in updated
    assert role_memory.read_member_pending()["items"] == []


def test_seconds_until_next_tick_aligns_to_interval_boundary():
    now = datetime(2026, 2, 23, 12, 34, 56)
    loop = MemoryOptimizerLoop(None, interval_seconds=3600, _now_fn=lambda: now)

    secs = loop._seconds_until_next_tick()

    assert abs(secs - (25 * 60 + 4)) < 0.001


def test_seconds_until_next_tick_always_positive():
    for h in range(24):
        now = datetime(2026, 2, 23, h, 59, 59)
        loop = MemoryOptimizerLoop(None, interval_seconds=300, _now_fn=lambda n=now: n)
        assert loop._seconds_until_next_tick() > 0


def test_memory_optimizer_loop_runs_global_and_role_optimizations(tmp_path):
    role_store = RoleStore(tmp_path)
    _ = role_store.create_role(
        role_id="mira",
        name="Mira",
        description="",
        system_prompt="you are mira",
    )

    optimizer = types.SimpleNamespace()
    calls: list[str | None] = []

    async def _optimize(*, role_id: str | None = None) -> None:
        calls.append(role_id)
        loop.stop()

    optimizer.optimize = _optimize
    optimizer._workspace = tmp_path
    loop = MemoryOptimizerLoop(optimizer, interval_seconds=60, _now_fn=lambda: datetime(2026, 2, 23, 12, 0, 0))

    original_sleep = asyncio.sleep

    async def _fast_sleep(_secs: float) -> None:
        return None

    try:
        asyncio.sleep = _fast_sleep  # type: ignore[assignment]
        asyncio.run(loop.run())
    finally:
        asyncio.sleep = original_sleep  # type: ignore[assignment]

    assert calls == ["mira"]


def test_memory_optimizer_loop_catches_up_overdue_roles_on_start(tmp_path):
    role_store = RoleStore(tmp_path)
    _ = role_store.create_role(
        role_id="mira",
        name="Mira",
        description="",
        system_prompt="you are mira",
    )
    optimizer = types.SimpleNamespace()
    calls: list[str | None] = []

    async def _optimize(*, role_id: str | None = None) -> None:
        calls.append(role_id)

    optimizer.optimize = _optimize
    optimizer._workspace = tmp_path
    loop = MemoryOptimizerLoop(
        optimizer,
        interval_seconds=3600,
        _now_fn=lambda: datetime(2026, 2, 23, 12, 0, 0),
    )

    asyncio.run(loop._catch_up_overdue_roles())

    assert calls == ["mira"]
