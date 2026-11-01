"""Tool calls a proactive tick makes through ``PROACTIVE_HOST``.

The kernel checks every call (``execute_tool``); a host tool then runs in the
role's user context (``run_host_tool``). Host ``Tool`` objects stay here: the
proactive code sees names, schemas and results.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextvars import ContextVar
from typing import Any

from agent.proactive_host.natural import record_tool_fact
from agent.tools.account_delivery import shared_account_delivery
from agent.tools.execution import ToolExecutionRequest, ToolExecutor
from conversation.service import desktop_thread_id
from session.manager.helpers import role_session_key
from shiori_sdk.core.proactive_host import (
    ProactiveToolCall,
    ProactiveToolInvoker,
    ProactiveToolOutcome,
)
from shiori_sdk.tools import ToolResult

# The tool name the kernel just allowed, while ``execute_tool`` runs its
# invoker. ``run_host_tool`` runs only that tool, so a host tool never runs
# without the core checks (shell interception, kernel ``ToolCalling``).
_CHECKED_TOOL: ContextVar[str | None] = ContextVar(
    "proactive_checked_tool", default=None
)


async def execute_tool(
    core: Any, call: ProactiveToolCall, invoker: ProactiveToolInvoker
) -> ProactiveToolOutcome:
    """Run one call through ``core``'s kernel and record it on an open plan."""
    manager = core.plugin_manager
    if manager is None:
        raise RuntimeError("主动工具需要已启动的插件内核")
    executor = ToolExecutor(lambda: manager.kernel)

    async def run(name: str, arguments: dict[str, Any]) -> object:
        token = _CHECKED_TOOL.set(name)
        try:
            return await invoker(name, arguments)
        finally:
            _CHECKED_TOOL.reset(token)

    result = await executor.execute(
        ToolExecutionRequest(
            call_id=call.call_id,
            tool_name=call.name,
            arguments=dict(call.arguments),
            source="proactive",
            session_key=call.session_key,
            channel=call.channel,
            chat_id=call.chat_id,
        ),
        run,
    )
    # The text the proactive and Drift tool loops record.
    text = str(result.output)
    record_tool_fact(call.call_id, call.name, call.arguments, text)
    return ProactiveToolOutcome(
        text=text,
        status=result.status,
        arguments=result.final_arguments,
        finalize=result.finalize,
    )


def require_checked_tool(name: str) -> None:
    """Raise ``PermissionError`` unless ``execute_tool`` just allowed ``name``."""
    if _CHECKED_TOOL.get() != name:
        raise PermissionError(f"宿主工具只能在已通过核心校验的调用里执行: {name}")


async def run_host_tool(
    core: Any, name: str, arguments: Mapping[str, object], *, role_id: str
) -> str | ToolResult:
    """Run a registered tool with only the role's user-context identity.

    Only the tool ``execute_tool`` has just allowed, from inside its invoker;
    anything else raises ``PermissionError`` before the tool is looked up. A
    tool reads its identity only from the keys it declares in
    ``context_precedence``; it gets the role, the role session as the turn
    session and the desktop thread for those, and nothing else.
    """
    require_checked_tool(name)
    if not role_id:
        raise ValueError("宿主工具需要角色")
    tool = core.tools.get_tool(name)
    if tool is None:
        raise LookupError(f"宿主工具不存在: {name}")
    identity = {
        "role_id": role_id,
        "turn_session_key": role_session_key(role_id),
        "thread_id": desktop_thread_id(role_id),
    }
    declared = getattr(tool, "context_precedence", frozenset())
    return await core.tools.execute(
        name,
        dict(arguments),
        context={key: value for key, value in identity.items() if key in declared},
    )


def tool_schemas(
    core: Any, names: Sequence[str] | None
) -> tuple[Mapping[str, object], ...]:
    """Schemas from the generation's registry, in the requested order."""
    selected = None if names is None else list(names)
    return tuple(core.tools.get_schemas(selected))


def mcp_server_names(core: Any) -> tuple[str, ...]:
    """MCP servers that currently have tools on the generation, sorted."""
    return tuple(sorted(core.tools.get_mcp_server_names()))


def mcp_tool_names(core: Any, server: str) -> tuple[str, ...]:
    """The tools ``server`` currently has on the generation, sorted."""
    return tuple(sorted(core.tools.get_tool_names_by_source("mcp", server)))


def require_channel_account(core: Any, role_id: str, channel: str) -> None:
    """Raise unless ``role_id`` has an account on ``channel``."""
    delivery = shared_account_delivery(core.tools)
    if delivery is None:
        raise RuntimeError("账号目标发送服务不可用")
    delivery.channel_account(channel, role_id)
