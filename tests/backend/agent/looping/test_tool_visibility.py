"""
tool_search 可见性机制回归测试。

覆盖场景：
- tool_search_enabled=True 时非存在工具被拦截
- tool_search_enabled=True 时存在但不可见的工具自动解锁
- tool_search 调用结果正确扩展 visible_names
- tool_search 解锁名单写入 tool_chain，供后续轮次从历史恢复
- preloaded 工具在下一请求中直接可见
"""

import asyncio
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock

from agent.looping.core import AgentLoop
from agent.looping.ports import (
    AgentLoopConfig,
    AgentLoopDeps,
    LLMConfig,
    MemoryServices,
)


from agent.provider import LLMResponse, ToolCall
from agent.tools.base import Tool
from agent.tools.registry import ToolRegistry
from agent.tools.tool_search import ToolSearchTool
from tests.backend.memory_fakes import FakeMemoryEngine

# ── 工具桩 ────────────────────────────────────────────────────────────────────


class _DummyTool(Tool):
    def __init__(self, name: str) -> None:
        self._name = name
        self.calls: list[dict] = []

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return f"dummy tool {self._name}"

    @property
    def parameters(self) -> dict:
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs: Any) -> str:
        self.calls.append(kwargs)
        return f"ok:{self._name}"


class _FakeProvider:
    def __init__(self, responses: list[LLMResponse]) -> None:
        self._responses = list(responses)

    async def chat(self, **kwargs: Any) -> LLMResponse:
        if not self._responses:
            raise AssertionError("provider.chat called more times than expected")
        return self._responses.pop(0)


# ── 工厂 ──────────────────────────────────────────────────────────────────────


def _make_loop(
    tmp_path: Path,
    provider: _FakeProvider,
    registry: ToolRegistry,
    tool_search_enabled: bool = True,
) -> AgentLoop:
    return AgentLoop(
        AgentLoopDeps(
            bus=MagicMock(),
            provider=cast(Any, provider),
            tools=registry,
            session_manager=MagicMock(),
            workspace=tmp_path,
            memory_services=MemoryServices(engine=FakeMemoryEngine(tmp_path)),
        ),
        AgentLoopConfig(
            llm=LLMConfig(max_iterations=10, tool_search_enabled=tool_search_enabled)
        ),
    )


def _base_registry() -> ToolRegistry:
    """只含 tool_search 的最小 registry。"""
    reg = ToolRegistry()
    reg.register(ToolSearchTool(reg), always_on=True, risk="read-only")
    return reg


# ── 可见性 / 拦截测试 ─────────────────────────────────────────────────────────


class TestVisibilityGuard:
    def test_nonexistent_tool_is_blocked(self, tmp_path):
        """完全不在 registry 里的工具名 → 拦截，不执行，返回错误消息给模型。"""
        reg = _base_registry()
        provider = _FakeProvider(
            [
                LLMResponse(content="", tool_calls=[ToolCall("c1", "ghost_tool", {})]),
                LLMResponse(content="ok", tool_calls=[]),
            ]
        )
        loop = _make_loop(tmp_path, provider, reg)

        final, tools_used, _, _, _ = asyncio.run(
            loop._run_agent_loop([{"role": "user", "content": "test"}])
        )

        assert final == "ok"
        assert "ghost_tool" not in tools_used  # 被拦截，不计入 tools_used

    def test_deferred_tool_direct_call_blocked_with_select_hint(self, tmp_path):
        """在 registry 里但不在 visible_names 里的工具（deferred）直接调用
        → 不执行，返回 select: 引导错误，模型收到后给出最终回复。"""
        reg = _base_registry()
        hidden = _DummyTool("hidden_tool")
        reg.register(hidden)  # 不设 always_on → deferred

        provider = _FakeProvider(
            [
                LLMResponse(content="", tool_calls=[ToolCall("c1", "hidden_tool", {})]),
                LLMResponse(content="done", tool_calls=[]),
            ]
        )
        loop = _make_loop(tmp_path, provider, reg)

        final, tools_used, tool_chain, _, _ = asyncio.run(
            loop._run_agent_loop([{"role": "user", "content": "test"}])
        )

        assert final == "done"
        assert "hidden_tool" not in tools_used  # 未执行，不计入 tools_used
        assert len(hidden.calls) == 0  # 工具实体未被调用

        # 第一轮 tool_chain 应有 select: 引导错误
        calls = tool_chain[0]["calls"] if tool_chain else []
        hidden_call = next((c for c in calls if c["name"] == "hidden_tool"), None)
        assert hidden_call is not None
        assert "select:" in hidden_call["result"]

    def test_tool_search_enabled_false_exposes_all_tools(self, tmp_path):
        """tool_search_enabled=False 时全量暴露，hidden tool 直接可用。"""
        reg = _base_registry()
        hidden = _DummyTool("hidden_tool")
        reg.register(hidden)

        provider = _FakeProvider(
            [
                LLMResponse(content="", tool_calls=[ToolCall("c1", "hidden_tool", {})]),
                LLMResponse(content="done", tool_calls=[]),
            ]
        )
        loop = _make_loop(tmp_path, provider, reg, tool_search_enabled=False)

        _, tools_used, _, _, _ = asyncio.run(
            loop._run_agent_loop([{"role": "user", "content": "test"}])
        )

        assert "hidden_tool" in tools_used

    def test_tool_search_result_unlocks_target_tool(self, tmp_path):
        """调用 tool_search 后，返回结果里的工具名加入 visible_names。"""
        reg = _base_registry()
        target = _DummyTool("target_tool")
        reg.register(target)

        provider = _FakeProvider(
            [
                # 第 1 轮：调用 tool_search
                LLMResponse(
                    content="",
                    tool_calls=[ToolCall("s1", "tool_search", {"query": "target"})],
                ),
                # 第 2 轮：调用解锁后的 target_tool
                LLMResponse(content="", tool_calls=[ToolCall("t1", "target_tool", {})]),
                # 第 3 轮：返回最终结果
                LLMResponse(content="all done", tool_calls=[]),
            ]
        )
        loop = _make_loop(tmp_path, provider, reg)

        final, tools_used, _, _, _ = asyncio.run(
            loop._run_agent_loop([{"role": "user", "content": "use target"}])
        )

        assert "target_tool" in tools_used
        assert len(target.calls) == 1
        assert final == "all done"

    def test_visible_names_starts_with_only_always_on(self, tmp_path):
        """tool_search_enabled=True 时，第一次 LLM 调用只传 always_on 工具 schema。"""
        reg = _base_registry()
        hidden = _DummyTool("hidden_tool")
        reg.register(hidden)

        schemas_seen: list[list[str]] = []

        class _CapturingProvider:
            _responses = [LLMResponse(content="done", tool_calls=[])]

            async def chat(self, **kwargs: Any) -> LLMResponse:
                schemas_seen.append(
                    [t["function"]["name"] for t in (kwargs.get("tools") or [])]
                )
                return self._responses.pop(0)

        loop = _make_loop(tmp_path, cast(Any, _CapturingProvider()), reg)

        asyncio.run(loop._run_agent_loop([{"role": "user", "content": "test"}]))

        assert schemas_seen, "provider.chat was never called"
        first_call_tools = schemas_seen[0]
        assert "tool_search" in first_call_tools
        assert "hidden_tool" not in first_call_tools

    def test_unlocked_schema_appends_after_always_on(self, tmp_path):
        reg = ToolRegistry()
        hidden = _DummyTool("early_hidden")
        reg.register(hidden)
        reg.register(ToolSearchTool(reg), always_on=True, risk="read-only")

        schemas_seen: list[list[str]] = []
        messages_seen: list[list[dict[str, Any]]] = []

        class _CapturingProvider(_FakeProvider):
            async def chat(self, **kwargs: Any) -> LLMResponse:
                schemas_seen.append(
                    [t["function"]["name"] for t in (kwargs.get("tools") or [])]
                )
                messages_seen.append(list(kwargs.get("messages") or []))
                return await super().chat(**kwargs)

        provider = _CapturingProvider(
            [
                LLMResponse(
                    content="",
                    tool_calls=[
                        ToolCall("s1", "tool_search", {"query": "select:early_hidden"})
                    ],
                ),
                LLMResponse(
                    content="", tool_calls=[ToolCall("h1", "early_hidden", {})]
                ),
                LLMResponse(content="done", tool_calls=[]),
            ]
        )
        loop = _make_loop(tmp_path, provider, reg)

        final, tools_used, _, _, _ = asyncio.run(
            loop._run_agent_loop([{"role": "user", "content": "use hidden"}])
        )

        assert final == "done"
        assert "early_hidden" in tools_used
        assert schemas_seen[0] == ["tool_search"]
        assert schemas_seen[1] == ["tool_search", "early_hidden"]
        second_call_text = "\n".join(
            str(message.get("content") or "") for message in messages_seen[1]
        )
        assert "当前工具状态" not in second_call_text


# ── 跨轮可见性 ────────────────────────────────────────────────────────────────


class TestCrossTurnVisibility:
    def test_tool_search_records_unlocked_names_in_tool_chain(self, tmp_path):
        """解锁后本轮未调用的工具也要落进 tool_chain，下一轮才能从历史恢复。"""
        reg = _base_registry()
        reg.register(_DummyTool("target_tool"))
        provider = _FakeProvider(
            [
                LLMResponse(
                    content="",
                    tool_calls=[
                        ToolCall("s1", "tool_search", {"query": "select:target_tool"})
                    ],
                ),
                LLMResponse(content="要现在执行吗？", tool_calls=[]),
            ]
        )
        loop = _make_loop(tmp_path, provider, reg)

        _, _, tool_chain, _, _ = asyncio.run(
            loop._run_agent_loop([{"role": "user", "content": "use target"}])
        )

        search_call = tool_chain[0]["calls"][0]
        assert search_call["name"] == "tool_search"
        assert search_call["unlocked"] == ["target_tool"]

    def test_preloaded_tool_visible_on_first_request(self, tmp_path):
        """从历史推导出的 preloaded 工具在下一请求首轮即可见并可直接调用。"""
        reg = _base_registry()
        target = _DummyTool("remembered_tool")
        reg.register(target)
        schemas_seen: list[list[str]] = []

        class _CapturingProvider(_FakeProvider):
            async def chat(self, **kwargs: Any) -> LLMResponse:
                schemas_seen.append(
                    [t["function"]["name"] for t in (kwargs.get("tools") or [])]
                )
                return await super().chat(**kwargs)

        provider = _CapturingProvider(
            [
                LLMResponse(
                    content="", tool_calls=[ToolCall("c1", "remembered_tool", {})]
                ),
                LLMResponse(content="done", tool_calls=[]),
            ]
        )
        loop = _make_loop(tmp_path, provider, reg)

        final, tools_used, _, _, _ = asyncio.run(
            loop._run_agent_loop(
                [{"role": "user", "content": "again"}],
                preloaded_tools={"remembered_tool"},
            )
        )

        assert final == "done"
        assert schemas_seen[0] == ["tool_search", "remembered_tool"]
        assert "remembered_tool" in tools_used
        assert len(target.calls) == 1
