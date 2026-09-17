from __future__ import annotations

import asyncio
from typing import Any

from agent.tool_hooks.base import ToolHook
from agent.tool_hooks.executor import ToolExecutor
from agent.tool_hooks.types import (
    HookContext,
    HookOutcome,
    ToolExecutionRequest,
    ToolExecutionResult,
    is_finalize_denial,
)


class _SpyHook(ToolHook):
    def __init__(
        self,
        *,
        name: str,
        event: str,
        matched: bool = True,
        outcome: HookOutcome | None = None,
    ) -> None:
        self.name = name
        self.event = event
        self._matched = matched
        self._outcome = outcome or HookOutcome()
        self.calls: list[HookContext] = []
        self._match_error: Exception | None = None
        self._run_error: Exception | None = None

    def matches(self, ctx: HookContext) -> bool:
        if self._match_error is not None:
            raise self._match_error
        return self._matched

    async def run(self, ctx: HookContext) -> HookOutcome:
        if self._run_error is not None:
            raise self._run_error
        self.calls.append(ctx)
        return self._outcome


async def _invoke(tool_name: str, arguments: dict[str, Any]) -> Any:
    return {"tool": tool_name, "arguments": dict(arguments)}


def test_tool_executor_pre_hook_can_update_arguments() -> None:
    hook = _SpyHook(
        name="rewrite",
        event="pre_tool_use",
        outcome=HookOutcome(updated_input={"x": 2}),
    )
    executor = ToolExecutor([hook])

    result = asyncio.run(
        executor.execute(
            ToolExecutionRequest(
                call_id="c1",
                tool_name="dummy",
                arguments={"x": 1},
                source="passive",
            ),
            _invoke,
        )
    )

    assert result.status == "success"
    assert result.final_arguments == {"x": 2}
    assert result.output == {"tool": "dummy", "arguments": {"x": 2}}
    assert hook.calls[0].request.arguments == {"x": 1}


def test_tool_executor_denied_is_not_error() -> None:
    hook = _SpyHook(
        name="deny",
        event="pre_tool_use",
        outcome=HookOutcome(decision="deny", reason="blocked"),
    )
    executor = ToolExecutor([hook])

    result = asyncio.run(
        executor.execute(
            ToolExecutionRequest(
                call_id="c1",
                tool_name="dummy",
                arguments={"x": 1},
                source="passive",
            ),
            _invoke,
        )
    )

    assert result.status == "denied"
    assert result.output == "blocked"
    # 普通 deny：HookOutcome 没有设置 finalize，结果和 trace 都保持默认 False，
    # 不能被误判为结构化收尾意图（#239 AC2）。
    assert result.finalize is False
    assert result.pre_hook_trace[0].finalize is False
    assert is_finalize_denial(result) is False


def test_tool_executor_deny_with_finalize_propagates_onto_result_and_trace() -> None:
    """#239：任意 hook 都能用 HookOutcome.finalize 表达结构化收尾意图，
    ToolExecutor 把它原样透传到 ToolExecutionResult 和 HookTraceItem 上，
    而不是让宿主靠 reason 字符串前缀猜插件身份。"""
    hook = _SpyHook(
        name="plugin:budget_watchdog:enforce",
        event="pre_tool_use",
        outcome=HookOutcome(decision="deny", reason="预算耗尽", finalize=True),
    )
    executor = ToolExecutor([hook])

    result = asyncio.run(
        executor.execute(
            ToolExecutionRequest(
                call_id="c1",
                tool_name="dummy",
                arguments={"x": 1},
                source="passive",
            ),
            _invoke,
        )
    )

    assert result.status == "denied"
    assert result.output == "预算耗尽"
    assert result.finalize is True
    assert result.pre_hook_trace[0].finalize is True
    assert is_finalize_denial(result) is True


def test_preflight_propagates_finalize_from_a_deny_outcome() -> None:
    """``preflight`` 走的是 deferred/unlocked 工具那条分支，同样必须透传
    finalize，宿主的截断判断在两条分支上一致。"""
    hook = _SpyHook(
        name="plugin:budget_watchdog:enforce",
        event="pre_tool_use",
        outcome=HookOutcome(decision="deny", reason="预算耗尽", finalize=True),
    )
    executor = ToolExecutor([hook])

    result = asyncio.run(
        executor.preflight(
            ToolExecutionRequest(
                call_id="c1",
                tool_name="dummy",
                arguments={"x": 1},
                source="passive",
            )
        )
    )

    assert result.status == "denied"
    assert result.finalize is True
    assert is_finalize_denial(result) is True


def test_is_finalize_denial_requires_denied_status() -> None:
    """finalize 字段只在 status == "denied" 时有意义；即便某处误把它设成
    True，只要状态不是 denied，就不应该被当成收尾信号。"""
    success = ToolExecutionResult(
        status="success", output="ok", final_arguments={}, finalize=True
    )
    assert is_finalize_denial(success) is False


def test_tool_executor_post_hook_only_adds_extra_message() -> None:
    hook = _SpyHook(
        name="post",
        event="post_tool_use",
        outcome=HookOutcome(extra_message="hint"),
    )
    executor = ToolExecutor([hook])

    result = asyncio.run(
        executor.execute(
            ToolExecutionRequest(
                call_id="c1",
                tool_name="dummy",
                arguments={"x": 1},
                source="passive",
            ),
            _invoke,
        )
    )

    assert result.status == "success"
    assert result.output == {"tool": "dummy", "arguments": {"x": 1}}
    assert result.extra_messages == ["hint"]


def test_tool_executor_post_error_hook_cannot_swallow_error() -> None:
    hook = _SpyHook(
        name="post_error",
        event="post_tool_error",
        outcome=HookOutcome(extra_message="logged"),
    )
    executor = ToolExecutor([hook])

    async def _broken(_tool_name: str, _arguments: dict[str, Any]) -> Any:
        raise RuntimeError("boom")

    result = asyncio.run(
        executor.execute(
            ToolExecutionRequest(
                call_id="c1",
                tool_name="dummy",
                arguments={},
                source="passive",
            ),
            _broken,
        )
    )

    assert result.status == "error"
    assert result.output == "工具执行出错: boom"
    assert result.extra_messages == ["logged"]


def test_tool_executor_hook_exception_becomes_controlled_error() -> None:
    hook = _SpyHook(name="boom_hook", event="pre_tool_use")
    hook._run_error = RuntimeError("hook boom")
    executor = ToolExecutor([hook])

    result = asyncio.run(
        executor.execute(
            ToolExecutionRequest(
                call_id="c1",
                tool_name="dummy",
                arguments={"x": 1},
                source="passive",
            ),
            _invoke,
        )
    )

    assert result.status == "error"
    assert "boom_hook" in result.output
    assert "hook boom" in result.output


def test_tool_executor_post_tool_use_hook_failure_does_not_pollute_success() -> None:
    hook = _SpyHook(name="boom_hook", event="post_tool_use")
    hook._run_error = RuntimeError("post hook boom")
    executor = ToolExecutor([hook])

    result = asyncio.run(
        executor.execute(
            ToolExecutionRequest(
                call_id="c1",
                tool_name="dummy",
                arguments={"x": 1},
                source="passive",
            ),
            _invoke,
        )
    )

    assert result.status == "success"
    assert result.output == {"tool": "dummy", "arguments": {"x": 1}}
    assert result.post_hook_trace[-1].reason == "hook failed: post hook boom"
