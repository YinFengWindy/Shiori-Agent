from __future__ import annotations

from pydantic import BaseModel, Field

_DEFAULT_REPEAT_LIMIT = 3


class ToolLoopGuardConfig(BaseModel):
    """``[plugins.tool_loop_guard]`` config schema: validated via ``plugin.config.*``.

    ``repeat_limit`` 的下限沿用迁移前的硬编码约束（``max(2, int(raw_limit))``）：
    低于 2 时"连续重复"这个概念本身就没有意义（1 次调用不构成"重复"）。
    迁移前非法输入（非整数、或 < 2）会被静默吞掉、退回默认值 3；现在改为在
    配置边界直接拒绝并给出诊断，而不是让插件在运行时悄悄改写用户的配置意图。
    """

    repeat_limit: int = Field(
        default=_DEFAULT_REPEAT_LIMIT,
        ge=2,
        title="重复调用上限",
        description="以相同参数连续调用同一工具达到该次数时截断并收尾，最小为 2",
        json_schema_extra={"unit": "次"},
    )
