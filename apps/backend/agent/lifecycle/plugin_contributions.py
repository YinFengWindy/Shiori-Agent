"""插件贡献的实时视图：阶段模块与工具 hook 每次使用时从插件内核读取。

插件内核（``PluginKernel``）的同名属性每次访问都只汇总当前 ACTIVE 插件的贡献，
所以消费方持有内核本身而不是启动时复制的列表（派生对象的按需重建见
``core.common.live_contributions``）：插件在代内被卸载后下一次回合/
工具调用不再执行它的贡献，新加载的插件下一次即生效。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from agent.tool_hooks.base import ToolHook


class PluginContributionSource(Protocol):
    """当前 ACTIVE 插件的阶段模块与工具 hook；每次读取都反映最新启停状态。"""

    @property
    def before_turn_modules(self) -> Sequence[object]: ...

    @property
    def before_reasoning_modules(self) -> Sequence[object]: ...

    @property
    def prompt_render_modules(self) -> Sequence[object]: ...

    @property
    def before_step_modules(self) -> Sequence[object]: ...

    @property
    def after_step_modules(self) -> Sequence[object]: ...

    @property
    def after_reasoning_modules(self) -> Sequence[object]: ...

    @property
    def after_turn_modules(self) -> Sequence[object]: ...

    @property
    def tool_hooks(self) -> Sequence["ToolHook"]: ...


class _NoPluginContributions:
    """未接插件内核时的空来源。"""

    before_turn_modules: Sequence[object] = ()
    before_reasoning_modules: Sequence[object] = ()
    prompt_render_modules: Sequence[object] = ()
    before_step_modules: Sequence[object] = ()
    after_step_modules: Sequence[object] = ()
    after_reasoning_modules: Sequence[object] = ()
    after_turn_modules: Sequence[object] = ()
    tool_hooks: Sequence["ToolHook"] = ()


NO_PLUGIN_CONTRIBUTIONS: PluginContributionSource = _NoPluginContributions()
