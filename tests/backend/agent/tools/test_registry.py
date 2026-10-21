"""ToolRegistry 的参数限制、schema 顺序和执行上下文。"""

import asyncio
import json
from typing import Any

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


class _StubTool(Tool):
    def __init__(self, name: str, description: str) -> None:
        self._name = name
        self._description = description

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs: Any) -> str:
        return "ok"


class _PathOnlyTool(Tool):
    name = "path_only"
    description = "测试只接收 path 的工具"
    parameters = {
        "type": "object",
        "properties": {"path": {"type": "string", "description": "路径"}},
        "required": ["path"],
    }

    async def execute(self, path: str) -> str:
        return path


class _ExistingDescriptionTool(Tool):
    name = "existing_description"
    description = "测试自带 description 参数的工具"
    parameters = {
        "type": "object",
        "properties": {
            "description": {"type": "string", "description": "业务描述"},
        },
        "required": ["description"],
    }

    async def execute(self, description: str) -> str:
        return description


class _ContextEchoTool(Tool):
    name = "context_echo"
    description = "回显工具执行上下文"
    parameters = {"type": "object", "properties": {}, "required": []}

    async def execute(
        self,
        session_key: str = "",
        role_id: str = "",
        channel: str = "",
        chat_id: str = "",
        **_: Any,
    ) -> str:
        return json.dumps(
            {
                "session_key": session_key,
                "role_id": role_id,
                "channel": channel,
                "chat_id": chat_id,
            },
            ensure_ascii=False,
        )


def test_registry_adds_model_description_for_progress() -> None:
    reg = ToolRegistry()
    reg.register(_PathOnlyTool())

    schema = reg.get_schemas(names={"path_only"})[0]["function"]["parameters"]

    assert "description" in schema["properties"]
    assert "description" in schema["required"]
    assert "description" not in _PathOnlyTool.parameters["properties"]


def test_registry_get_schemas_preserves_explicit_name_order() -> None:
    reg = ToolRegistry()
    reg.register(_StubTool("hidden_first", "先注册的隐藏工具"))
    reg.register(_StubTool("always_later", "后注册的常驻工具"), always_on=True)

    schemas = reg.get_schemas(names=["always_later", "hidden_first"])

    assert [schema["function"]["name"] for schema in schemas] == [
        "always_later",
        "hidden_first",
    ]


async def test_registry_strips_progress_description_before_execute() -> None:
    reg = ToolRegistry()
    reg.register(_PathOnlyTool())

    result = await reg.execute(
        "path_only",
        {"path": "/tmp/a", "description": "读取文件"},
    )

    assert result == "/tmp/a"


async def test_registry_keeps_real_description_parameter() -> None:
    reg = ToolRegistry()
    reg.register(_ExistingDescriptionTool())

    result = await reg.execute(
        "existing_description",
        {"description": "业务描述"},
    )

    assert result == "业务描述"


async def test_registry_execute_prefers_explicit_context_snapshot() -> None:
    reg = ToolRegistry()
    reg.register(_ContextEchoTool())
    reg.set_context(
        session_key="stale-session",
        role_id="stale-role",
        channel="stale-channel",
        chat_id="stale-chat",
    )

    first, second = await asyncio.gather(
        reg.execute(
            "context_echo",
            {},
            context={
                "session_key": "session-a",
                "role_id": "role-a",
                "channel": "telegram",
                "chat_id": "100",
            },
        ),
        reg.execute(
            "context_echo",
            {},
            context={
                "session_key": "session-b",
                "role_id": "role-b",
                "channel": "discord",
                "chat_id": "200",
            },
        ),
    )

    assert json.loads(first) == {
        "session_key": "session-a",
        "role_id": "role-a",
        "channel": "telegram",
        "chat_id": "100",
    }
    assert json.loads(second) == {
        "session_key": "session-b",
        "role_id": "role-b",
        "channel": "discord",
        "chat_id": "200",
    }


def test_registry_get_context_returns_copy() -> None:
    reg = ToolRegistry()
    reg.set_context(channel="telegram", chat_id="123")

    ctx = reg.get_context()
    ctx["channel"] = "mutated"

    assert reg.get_context() == {"channel": "telegram", "chat_id": "123"}


async def test_registry_context_is_task_local() -> None:
    reg = ToolRegistry()
    first_ready = asyncio.Event()
    second_ready = asyncio.Event()

    async def _first() -> dict[str, str]:
        reg.set_context(channel="telegram", chat_id="123")
        first_ready.set()
        await second_ready.wait()
        return reg.get_context()

    async def _second() -> dict[str, str]:
        await first_ready.wait()
        reg.set_context(channel="discord", chat_id="999")
        second_ready.set()
        return reg.get_context()

    first, second = await asyncio.gather(_first(), _second())

    assert first == {"channel": "telegram", "chat_id": "123"}
    assert second == {"channel": "discord", "chat_id": "999"}
