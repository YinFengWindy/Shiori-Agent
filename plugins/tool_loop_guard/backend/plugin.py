from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from agent.lifecycle.types import PreToolCtx
from agent.tool_hooks import HookOutcome

from .config import ToolLoopGuardConfig

if TYPE_CHECKING:
    from agent.plugin_host.runtime_context import PluginRuntimeContext

_EXCLUDED_TOOLS = frozenset({"task_output", "task_stop"})


@dataclass
class _LoopState:
    signature: str = ""
    repeat_count: int = 0


class _ToolLoopGuard:
    """检测连续重复的工具调用并提前截断；v2 插件不再继承旧 Plugin ABC。"""

    def __init__(self, repeat_limit: int) -> None:
        self._states: dict[str, _LoopState] = {}
        self._repeat_limit = repeat_limit

    async def detect_repeated_tool_call(self, event: PreToolCtx) -> HookOutcome | None:
        signature, active_index = self._event_signature(event)
        if not signature or event.tool_batch_index != active_index:
            return None
        state_key = self._state_key(event)
        state = self._states.setdefault(state_key, _LoopState())
        if signature == state.signature:
            state.repeat_count += 1
        else:
            state.signature = signature
            state.repeat_count = 1
        if state.repeat_count < self._repeat_limit:
            return None
        return HookOutcome(
            decision="deny",
            reason=(f"连续重复调用工具 {state.repeat_count} 次，已截断并进入收尾。"),
            # 结构化收尾意图（见 agent.tool_hooks.HookOutcome.finalize）：宿主
            # 靠这个字段截断剩余批次并进入既有总结流程，不再靠 reason 前缀
            # 猜插件身份——任何插件都能用同一个字段表达"该收尾了"。
            finalize=True,
        )

    def _state_key(self, event: PreToolCtx) -> str:
        if event.session_key:
            return f"{event.source}:{event.session_key}"
        return f"{event.source}:{event.channel}:{event.chat_id}"

    def _signature(self, tool_name: str, arguments: dict[str, Any]) -> str:
        args = json.dumps(arguments, ensure_ascii=False, sort_keys=True)
        return f"{tool_name}:{args}"

    def _event_signature(self, event: PreToolCtx) -> tuple[str, int]:
        if not event.tool_batch:
            if event.tool_name in _EXCLUDED_TOOLS:
                return "", 0
            return self._signature(event.tool_name, event.arguments), 0

        parts: list[str] = []
        active_index = -1
        for index, tool_call in enumerate(event.tool_batch):
            tool_name = str(tool_call.get("name", ""))
            if tool_name in _EXCLUDED_TOOLS:
                continue
            arguments = tool_call.get("arguments")
            if not isinstance(arguments, dict):
                arguments = {}
            if active_index < 0:
                active_index = index
            parts.append(self._signature(tool_name, cast("dict[str, Any]", arguments)))
        if active_index < 0:
            return "", 0
        return "|".join(parts), active_index


async def setup(ctx: "PluginRuntimeContext") -> None:
    """装配 tool_loop_guard：读取 repeat_limit 配置，注册 pre-tool hook。

    hook 名由 ToolHooksCapability 统一生成（plugin:{plugin_id}:{handler.__name__}），
    插件不再直接引用宿主的 PluginToolHook 或自行拼接 hook 名（#182 评审）。

    行为变化说明：旧 Plugin ABC 版本没有 ConfigModel / _conf_schema.json，
    因此旧 self.context.config 恒为 None，repeat_limit 实际上永远是这里的硬编码默认值 3，
    用户在 [plugins.tool_loop_guard] 里配置的 repeat_limit 从未生效过。迁移到 v2 后
    ctx.config 读的是 PluginConfig(services.plugin_configs[id])，配置现在真的会生效
    （见 tests/plugins/tool_loop_guard/test_plugin.py 的
    test_repeat_limit_config_actually_takes_effect_after_v2_migration）。
    这是修正一个既有 bug，不是刻意的新行为，默认值仍是 3。

    #239：manifest 现在声明了 config_model（``ToolLoopGuardConfig``），所以这里
    不再需要 try/except 的临时兜底——非法配置（非整数、或 < 2）直接在这里
    model_validate 失败并抛出，由插件加载诊断呈现，不再被静默改写为默认值
    （与 novelai 的 ``NovelAIConfig.model_validate(ctx.config.as_dict())`` 用法一致）。
    """
    config = ToolLoopGuardConfig.model_validate(ctx.config.as_dict())
    guard = _ToolLoopGuard(config.repeat_limit)
    ctx.tool_hooks.add_handler(guard.detect_repeated_tool_call)
