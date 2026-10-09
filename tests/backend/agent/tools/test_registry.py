"""ToolRegistry 的外部上下文参数限制在注册时校验（#522）。"""

import pytest

from agent.tools.account_delivery import ACCOUNT_SEND_EXTERNAL_LIMIT
from shiori_sdk.tools import TOOL_ATTACHMENT_SCOPE_KEY, Tool, ToolAttachmentScope
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


async def test_attachment_scope_cannot_be_granted_by_model_arguments():
    class AttachmentTool(_NoTargetTool):
        context_precedence = frozenset({TOOL_ATTACHMENT_SCOPE_KEY})

        async def execute(self, **kwargs):
            self.scope = kwargs.get(TOOL_ATTACHMENT_SCOPE_KEY)
            return "ok"

    tool = AttachmentTool()
    tools = ToolRegistry()
    tools.register(tool)
    trusted = ToolAttachmentScope(channel="qq_bot", paths=("received.txt",))
    forged = {"channel": "qq_bot", "paths": ["private.txt"]}
    await tools.execute(
        tool.name,
        {TOOL_ATTACHMENT_SCOPE_KEY: forged},
        context={TOOL_ATTACHMENT_SCOPE_KEY: trusted},
    )
    assert tool.scope is trusted
    await tools.execute(tool.name, {TOOL_ATTACHMENT_SCOPE_KEY: forged}, context={})
    assert tool.scope is None


async def test_unrelated_tools_do_not_receive_attachment_scope_for_serialization():
    import json

    class ForwardedTool(_NoTargetTool):
        async def execute(self, **kwargs):
            return json.dumps(kwargs)

    tool = ForwardedTool()
    tools = ToolRegistry()
    tools.register(tool)
    result = await tools.execute(
        tool.name,
        {"message": "remember"},
        context={
            "channel": "qq",
            TOOL_ATTACHMENT_SCOPE_KEY: ToolAttachmentScope(
                channel="qq", paths=("private.txt",)
            ),
        },
    )
    assert json.loads(result) == {"channel": "qq", "message": "remember"}
