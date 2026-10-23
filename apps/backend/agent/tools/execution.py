"""One tool call through the plugin kernel: ``ToolCalling``, the tool, ``ToolCalled``.

Every tool loop (passive turn, proactive tick, drift, subagent) runs its calls
through ``ToolExecutor`` (#902): the ``ToolCalling`` chain may rewrite the
arguments or reject the call, the core checks of ``check_tool_call`` then judge
the final arguments, the tool runs, and the ``ToolCalled`` chain may rewrite
the result. A veto ends the call as ``denied`` with its reason as the result;
a ``ToolVeto`` with ``finalize`` asks the loop to close (see
``append_finalize_skipped_tool_results``).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent.tool_runtime import append_tool_result
from agent.tools.shell.guard import destructive_command_reason
from shiori_sdk.core.tools import (
    ToolCalled,
    ToolCalling,
    ToolSource,
    ToolStatus,
    ToolVeto,
)
from shiori_sdk.kernel import Kernel, Veto
from shiori_sdk.tools import ToolResult

ToolInvoker = Callable[[str, dict[str, Any]], Awaitable[Any]]
KernelSource = Callable[[], Kernel]
"""The kernel to emit through, read once per call: a generation switch or an
in-generation plugin reload takes effect on the next call."""
ToolAdmission = Callable[[str, dict[str, Any]], str | None]
"""A loop's own judgement of the final arguments: the refusal reason, or None."""

SHELL_TOOL = "shell"

# LLM 可见、非用户可见的通用收尾提示：任意插件触发结构化收尾意图时，
# 同一批次里被跳过的后续 tool_call 都用这条统一文案回填 tool result。
FINALIZE_SKIPPED_TOOL_CALL_MESSAGE = "工具调用已跳过：本轮工具调用已提前收尾。"

# The admission of the call being emitted, read by ``check_tool_call``.
_admission: ContextVar[ToolAdmission | None] = ContextVar(
    "tool_call_admission", default=None
)


@dataclass(frozen=True)
class ToolExecutionRequest:
    """The call a model asked for, before any plugin saw it."""

    call_id: str
    tool_name: str
    arguments: dict[str, Any]
    source: ToolSource
    session_key: str = ""
    channel: str = ""
    chat_id: str = ""
    tool_batch: tuple[dict[str, Any], ...] = ()
    tool_batch_index: int = 0


@dataclass(frozen=True)
class ToolExecutionResult:
    """How one call ended.

    ``final_arguments`` are the arguments the tool ran with; a rejected call
    keeps the model's own (a veto carries no event). ``finalize`` is only ever
    set on a ``denied`` result, from a ``ToolVeto(finalize=True)``.
    """

    status: ToolStatus
    output: Any
    final_arguments: dict[str, Any] = field(default_factory=dict[str, Any])
    finalize: bool = False


def install_tool_checks(kernel: Kernel, *, workspace: Path | None = None) -> None:
    """Adds ``check_tool_call`` to ``kernel``; ``workspace`` is guarded as a root."""
    protected = (workspace.resolve(),) if workspace is not None else ()

    async def check(event: ToolCalling) -> ToolCalling | Veto:
        return check_tool_call(event, protected_dirs=protected)

    kernel.check(ToolCalling, check)


def check_tool_call(
    event: ToolCalling, *, protected_dirs: Iterable[Path] = ()
) -> ToolCalling | Veto:
    """The core's fixed checks on a ``ToolCalling`` after the plugins' chain (D11).

    The calling loop's admission (the external-context tool limits of a
    restricted turn, #522) judges the final arguments first, then the minimal
    shell guard refuses a catastrophic ``shell`` command whoever wrote it.
    """
    arguments = dict(event.arguments)
    admission = _admission.get()
    if admission is not None and (reason := admission(event.tool_name, arguments)):
        return Veto(reason)
    if event.tool_name == SHELL_TOOL:
        command = str(arguments.get("command") or "")
        reason = destructive_command_reason(command, protected_dirs=protected_dirs)
        if reason is not None:
            return Veto(reason)
    return event


@contextmanager
def _admitting(admission: ToolAdmission | None):
    token = _admission.set(admission)
    try:
        yield
    finally:
        _admission.reset(token)


class ToolExecutor:
    """Runs single tool calls through the kernel ``kernel`` returns."""

    def __init__(self, kernel: KernelSource) -> None:
        self._kernel = kernel

    async def execute(
        self,
        request: ToolExecutionRequest,
        invoker: ToolInvoker,
        *,
        admission: ToolAdmission | None = None,
    ) -> ToolExecutionResult:
        """Emits ``ToolCalling``, runs ``invoker`` and emits ``ToolCalled``.

        ``invoker`` is the real tool entry (usually ``ToolRegistry.execute``).
        ``admission`` joins the core checks for this call, so it judges the
        arguments plugins rewrote. A tool error ends the call as ``error``.
        """
        kernel = self._kernel()
        decided = await self._calling(kernel, request, admission)
        if isinstance(decided, ToolExecutionResult):
            result = decided
        else:
            final_arguments = dict(decided.arguments)
            try:
                output = await invoker(request.tool_name, final_arguments)
            except Exception as error:
                result = ToolExecutionResult(
                    "error", f"工具执行出错: {error}", final_arguments
                )
            else:
                result = ToolExecutionResult("success", output, final_arguments)
        return await self._called(kernel, request, result)

    async def preflight(self, request: ToolExecutionRequest) -> ToolExecutionResult:
        """Emits ``ToolCalling`` for a call that will not run (its tool is hidden).

        The loop only learns whether a plugin asked to close the turn; nothing
        runs and no ``ToolCalled`` follows.
        """
        decided = await self._calling(self._kernel(), request, None)
        if isinstance(decided, ToolExecutionResult):
            return decided
        return ToolExecutionResult("success", "", dict(decided.arguments))

    async def _calling(
        self,
        kernel: Kernel,
        request: ToolExecutionRequest,
        admission: ToolAdmission | None,
    ) -> ToolCalling | ToolExecutionResult:
        event = ToolCalling(
            session_key=request.session_key,
            channel=request.channel,
            chat_id=request.chat_id,
            source=request.source,
            call_id=request.call_id,
            tool_name=request.tool_name,
            arguments=request.arguments,
            tool_batch=request.tool_batch,
            tool_batch_index=request.tool_batch_index,
        )
        with _admitting(admission):
            decided = await kernel.emit(event)
        if isinstance(decided, Veto):
            return ToolExecutionResult(
                "denied",
                decided.reason.strip() or "工具调用被拦截",
                dict(request.arguments),
                finalize=isinstance(decided, ToolVeto) and decided.finalize,
            )
        return decided

    async def _called(
        self, kernel: Kernel, request: ToolExecutionRequest, result: ToolExecutionResult
    ) -> ToolExecutionResult:
        text = _result_text(result.output)
        called = await kernel.emit(
            ToolCalled(
                session_key=request.session_key,
                channel=request.channel,
                chat_id=request.chat_id,
                source=request.source,
                call_id=request.call_id,
                tool_name=request.tool_name,
                arguments=result.final_arguments,
                status=result.status,
                result=text,
            )
        )
        if isinstance(called, Veto):
            raise RuntimeError(f"ToolCalled 不可否决，插件却否决了它: {called.reason}")
        if called.result == text:
            # Unchanged: keep the tool's own output, media and structure included.
            return result
        return ToolExecutionResult(
            result.status, called.result, result.final_arguments, result.finalize
        )


def _result_text(output: Any) -> str:
    return output.text if isinstance(output, ToolResult) else str(output)


def append_finalize_skipped_tool_results(
    messages: list[dict[str, Any]],
    skipped_tool_calls: Iterable[Any],
) -> None:
    """Backfills a tool result for every batch member a finalize skipped.

    Every ``tool_call`` in an assistant message must get a matching ``tool``
    result message, or a strict provider / session replay chokes on an
    unresolved ``tool_call_id``. The passive reasoning loop (both branches)
    and ``SubAgent`` close a truncated batch this way.
    """
    for skipped in skipped_tool_calls:
        append_tool_result(
            messages,
            tool_call_id=skipped.id,
            content=FINALIZE_SKIPPED_TOOL_CALL_MESSAGE,
            tool_name=skipped.name,
        )
