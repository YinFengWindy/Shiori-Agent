"""One tool call through the kernel: ToolCalling, core checks, the tool, ToolCalled."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from agent.tools.execution import ToolExecutionRequest, ToolExecutor
from shiori_sdk.core.tools import ToolCalled, ToolCalling, ToolVeto
from shiori_sdk.kernel import Veto
from shiori_sdk.tools import ToolResult
from tests.support.tool_calls import kernel_with


class _Tool:
    """Records the arguments it ran with and returns ``output``."""

    def __init__(self, output: Any = "ok") -> None:
        self.output = output
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, name: str, arguments: dict[str, Any]) -> Any:
        self.calls.append(arguments)
        if isinstance(self.output, Exception):
            raise self.output
        return self.output


def _request(name: str = "dummy", **arguments: Any) -> ToolExecutionRequest:
    return ToolExecutionRequest(
        call_id="c1", tool_name=name, arguments=arguments, source="passive"
    )


async def _set_x(event: ToolCalling) -> ToolCalling:
    return replace(event, arguments={**event.arguments, "x": 2})


async def _refuse(event: ToolCalling) -> Veto:
    return Veto("blocked")


async def _finalize(event: ToolCalling) -> ToolVeto:
    return ToolVeto("预算耗尽", finalize=True)


async def test_the_tool_runs_with_the_arguments_the_chain_left() -> None:
    tool, seen = _Tool(), []

    async def called(event: ToolCalled) -> ToolCalled:
        seen.append(dict(event.arguments))
        return event

    executor = ToolExecutor(lambda: kernel_with(_set_x, called=(called,)))
    result = await executor.execute(_request(x=1), tool)

    assert (result.status, result.final_arguments) == ("success", {"x": 2})
    assert tool.calls == [{"x": 2}]
    assert seen == [{"x": 2}]


async def test_a_veto_denies_the_call_without_running_the_tool() -> None:
    tool = _Tool()

    result = await ToolExecutor(lambda: kernel_with(_refuse)).execute(
        _request(x=1), tool
    )

    assert (result.status, result.output, result.finalize) == (
        "denied",
        "blocked",
        False,
    )
    assert tool.calls == []


async def test_a_finalizing_veto_asks_the_loop_to_close_in_both_paths() -> None:
    executor = ToolExecutor(lambda: kernel_with(_finalize))

    executed = await executor.execute(_request(), _Tool())
    preflight = await executor.preflight(_request())

    assert (executed.status, executed.finalize) == ("denied", True)
    assert (preflight.status, preflight.finalize) == ("denied", True)


async def test_a_tool_error_ends_the_call_as_error_and_still_reaches_tool_called() -> (
    None
):
    seen: list[str] = []

    async def called(event: ToolCalled) -> ToolCalled:
        seen.append(event.status)
        return event

    executor = ToolExecutor(lambda: kernel_with(called=(called,)))
    result = await executor.execute(_request(), _Tool(RuntimeError("boom")))

    assert (result.status, result.output) == ("error", "工具执行出错: boom")
    assert seen == ["error"]


async def test_only_a_changed_result_replaces_the_tools_own_result() -> None:
    media = ToolResult(text="图", content_blocks=[{"type": "image_url"}])

    async def same(event: ToolCalled) -> ToolCalled:
        return replace(event, result=event.result)

    async def note(event: ToolCalled) -> ToolCalled:
        return replace(event, result=event.result + "（已记录）")

    kept = await ToolExecutor(lambda: kernel_with(called=(same,))).execute(
        _request(), _Tool(media)
    )
    rewritten = await ToolExecutor(lambda: kernel_with(called=(note,))).execute(
        _request(), _Tool(media)
    )

    assert kept.output is media
    assert rewritten.output == "图（已记录）"


async def test_the_loops_admission_judges_the_arguments_a_plugin_rewrote() -> None:
    tool = _Tool()

    def admission(name: str, arguments: dict[str, Any]) -> str | None:
        return "x 不能是 2" if arguments.get("x") == 2 else None

    result = await ToolExecutor(lambda: kernel_with(_set_x)).execute(
        _request(x=1), tool, admission=admission
    )

    assert (result.status, result.output) == ("denied", "x 不能是 2")
    assert tool.calls == []


async def test_the_kernel_is_read_again_on_every_call() -> None:
    kernels = [kernel_with(_refuse), kernel_with()]
    executor = ToolExecutor(lambda: kernels[0])

    assert (await executor.execute(_request(), _Tool())).status == "denied"
    kernels.pop(0)
    assert (await executor.execute(_request(), _Tool())).status == "success"
