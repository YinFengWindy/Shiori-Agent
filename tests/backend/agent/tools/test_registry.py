"""ToolRegistry 的外部上下文参数限制在注册时校验（#522）。"""

import pytest

from agent.tools.account_delivery import ACCOUNT_SEND_EXTERNAL_LIMIT
from shiori_sdk.tools import Tool
from agent.tools.registry import ToolRegistry


class _NoTargetTool(Tool):
    name = "no_target"
    description = "没有 target_kind 参数"
    parameters = {"type": "object", "properties": {"message": {"type": "string"}}}

    async def execute(self, **kwargs):
        return "done"


def test_register_rejects_a_limit_on_an_undefined_argument():
    """参数限制指向工具 schema 里不存在的参数时，注册直接失败。"""
    tools = ToolRegistry()
    with pytest.raises(ValueError, match="target_kind"):
        tools.register(
            _NoTargetTool(),
            external_allowed=True,
            external_limit=ACCOUNT_SEND_EXTERNAL_LIMIT,
        )
    assert not tools.has_tool("no_target")
