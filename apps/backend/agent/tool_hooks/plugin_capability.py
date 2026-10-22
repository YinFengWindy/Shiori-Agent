"""The ``tool_hooks`` plugin capability: plugin pre-tool hooks for the ``ToolExecutor``.

``PluginToolHooks`` is the ``host.tool_hooks`` core service (#901 P2). It keeps
each plugin's contributed hooks and hands the executor those of the active
plugins, in the order the plugin kernel gives (dependency depth, then id).
"""

from __future__ import annotations

import inspect
import logging
from typing import Any, cast

from shiori_sdk.tool_hooks import HookOutcome, PreToolCtx

from agent.plugin_host.capabilities import ContributionsByPlugin, contribute_to_list
from agent.plugin_host.core_keys import PluginBinding
from agent.tool_hooks.base import ToolHook
from agent.tool_hooks.types import HookContext

logger = logging.getLogger(__name__)


class PluginToolHooks(ContributionsByPlugin[ToolHook]):
    """The ``host.tool_hooks`` core service of one plugin kernel generation."""

    def for_plugin(self, binding: PluginBinding) -> ToolHooksCapability:
        """The tool hooks capability of the plugin ``binding`` describes."""
        return ToolHooksCapability(self.of(binding.plugin_id), binding)


def build_hook_name(plugin_id: str, handler_name: str) -> str:
    """生成稳定的插件 tool hook 注册名。"""
    return f"plugin:{plugin_id}:{handler_name}"


class PluginToolHook(ToolHook):
    """将插件的 pre-tool handler 适配为 ToolExecutor 的 ToolHook 接口。"""

    event = "pre_tool_use"

    def __init__(
        self,
        name: str,
        handler: Any,
        tool_name_filter: str | None = None,
    ) -> None:
        self.name = name
        self._handler = handler
        self._tool_name_filter = tool_name_filter

    def matches(self, ctx: HookContext) -> bool:
        if self._tool_name_filter is None:
            return True
        return ctx.request.tool_name == self._tool_name_filter

    async def run(self, ctx: HookContext) -> HookOutcome:
        # 1. 构造 PreToolCtx（复制 arguments，避免插件直接改原对象）
        event = PreToolCtx(
            session_key=ctx.request.session_key,
            channel=ctx.request.channel,
            chat_id=ctx.request.chat_id,
            tool_name=ctx.request.tool_name,
            arguments=dict(ctx.current_arguments),
            call_id=ctx.request.call_id,
            source=ctx.request.source,
            request_text=ctx.request.request_text,
            tool_batch=ctx.request.tool_batch,
            tool_batch_index=ctx.request.tool_batch_index,
        )
        # 2. 调插件 handler，返回值决定行为
        result = self._handler(event)
        if inspect.isawaitable(result):
            result = await result
        # 3. None → 不改参；dict → 新 arguments；HookOutcome → 允许插件直接 deny
        if result is None:
            return HookOutcome()
        if isinstance(result, HookOutcome):
            return result
        if isinstance(result, dict):
            return HookOutcome(updated_input=cast("dict[str, Any]", result))
        return HookOutcome()


class ToolHooksCapability:
    """贡献工具执行前置 hook（ToolExecutor pre_hook 链）。

    hook 的 ``run`` 经过插件实例的调用闸门：代内重载会等待已进入的这一次执行；
    闸门关闭后 pre_tool_use hook 拒绝本次工具调用（不在无守卫时执行），
    其余 hook 直接放行。
    """

    def __init__(self, hooks: list[ToolHook], binding: PluginBinding) -> None:
        self._hooks = hooks
        self._binding = binding

    def add(self, hook: ToolHook) -> None:
        label = f"tool_hook:{getattr(hook, 'name', hook)}"
        self._binding.scope.ensure_active(label)
        self._binding.calls.guard_tool_hook(hook)
        contribute_to_list(self._hooks, hook, effects=self._binding.scope, label=label)

    def add_handler(
        self,
        handler: Any,
        *,
        tool_name_filter: str | None = None,
        handler_name: str | None = None,
    ) -> None:
        """把函数式 pre-tool handler 包装为 PluginToolHook 并登记。

        hook 名统一在这里生成（``build_hook_name``），插件不再需要各自导入宿主的
        ``PluginToolHook``、手写 f-string 拼接或维护 ``_PLUGIN_NAME`` 常量（#182 评审）。
        包装函数或 partial 可以显式提供 ``handler_name``，保持公开诊断名称稳定。
        """
        resolved_name = handler_name or getattr(handler, "__name__", repr(handler))
        hook = PluginToolHook(
            name=build_hook_name(self._binding.plugin_id, resolved_name),
            handler=handler,
            tool_name_filter=tool_name_filter,
        )
        self.add(hook)
        logger.info("插件 tool hook 已注册: %s", hook.name)
