"""Role tools over every agent of the configured Herdr session.

They act on the whole session, not per role, and run without confirmation.
A role's prompt or keys go through the panel's own sending path, recorded as
from that role; the destination of the report comes only from the host's
capture of the current tool turn, never from the model's arguments.
"""

import json
from typing import Any, cast

from shiori_sdk.background_results import BackgroundResults
from shiori_sdk.process_resources import PluginProcessResources
from shiori_sdk.roles import Roles
from shiori_sdk.tools import Tool, ToolsCapability

from .agent_control import UNCONFIRMED_CODES, CommandSource
from .agent_watch import OUTPUT_TAIL
from .agents import SessionAgents
from .cli import CommandError

COMMAND_TAIL = 20
"""Latest command records a read returns."""

_GUIDE = (
    "操作 Herdr 中已有的 agent 请用 herdr_list_agents / herdr_read_agent / "
    "herdr_prompt_agent / herdr_send_keys，不要用 shell 执行 herdr 命令；"
    "要在新的独立 worktree 开发并交付 Draft PR，用 herdr_start_task。"
)

_REPORT_NOTE = (
    "你已接手该 agent：它停下、卡住、关闭或追踪超时时，结果会回报给你和本聊天，"
    "不需要轮询。"
)

_DESCRIPTIONS = {
    "list": "列出 Herdr session 中的全部 coding agent（含用户手动打开的 Claude Code / "
    "Codex），按 workspace 分组，附 pane_id、状态、终端标题、工作目录和接手角色。",
    "read": "读取 Herdr 中指定 agent 的状态、终端标题、工作目录、终端最近输出与指令记录。",
    "prompt": "把文字作为 prompt 直接发给 Herdr 中已有的 agent，立即执行；你成为它的接手"
    "角色，它停下、卡住、关闭或追踪超时时回报给你。超时或未确认送达时不要重发。",
    "keys": "向 Herdr 中已有的 agent 按逻辑按键（如 enter、esc、ctrl+c、up、down），"
    "用于回答确认提示或中断；你成为它的接手角色，结果同样回报给你。",
}

_PANE = {"type": "string", "description": "agent 的 pane_id，来自 herdr_list_agents"}


def _error(code: str, message: str, **extra: object) -> str:
    return json.dumps(
        {"ok": False, "error": {"code": code, "message": message}, **extra},
        ensure_ascii=False,
    )


class AgentTool(Tool):
    """`herdr_list_agents`, `herdr_read_agent`, `herdr_prompt_agent` or `herdr_send_keys`."""

    def __init__(
        self,
        action: str,
        agents: SessionAgents,
        tools: ToolsCapability,
        roles: Roles,
        results: BackgroundResults,
        resources: PluginProcessResources,
    ) -> None:
        self.action, self.agents, self.tools = action, agents, tools
        self.roles, self.results, self.resources = roles, results, resources

    @property
    def name(self) -> str:
        return {
            "list": "herdr_list_agents",
            "read": "herdr_read_agent",
            "prompt": "herdr_prompt_agent",
            "keys": "herdr_send_keys",
        }[self.action]

    @property
    def description(self) -> str:
        return f"{_DESCRIPTIONS[self.action]}{_GUIDE}"

    @property
    def parameters(self) -> dict[str, Any]:
        table: dict[str, dict[str, object]] = {
            "list": {},
            "read": {"pane_id": _PANE},
            "prompt": {
                "pane_id": _PANE,
                "text": {"type": "string", "description": "发给 agent 的完整 prompt"},
            },
            "keys": {
                "pane_id": _PANE,
                "keys": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": '按顺序按下的 Herdr 逻辑按键名，如 ["enter"]、["ctrl+c"]',
                },
            },
        }
        properties = table[self.action]
        return {
            "type": "object",
            "properties": properties,
            "required": list(properties),
        }

    async def execute(self, **kwargs: Any) -> str:
        """Expected failures come back as `{ok: false, error: {code, message}}`."""
        if not self.resources.active:
            raise RuntimeError("插件配置已替换，请重新调用当前工具")
        try:
            if self.action == "list":
                return await self._list()
            if self.action == "read":
                return await self._read(kwargs.get("pane_id"))
            return await self._send(kwargs)
        except CommandError as error:
            if error.code in UNCONFIRMED_CODES:
                return _error(error.code, str(error), note=_REPORT_NOTE)
            return _error(error.code, str(error))
        except PermissionError as error:
            return _error("not_permitted", str(error))
        except ValueError as error:
            return _error("invalid_request", str(error))

    def _handler(self, pane_id: str) -> dict[str, str] | None:
        handover = self.agents.control.watcher.handover(
            self.agents.control.session, pane_id
        )
        return handover.as_dict() if handover else None

    async def _list(self) -> str:
        listed = await self.agents.list_agents({})
        for group in cast(list[dict[str, Any]], listed["workspaces"]):
            for agent in cast(list[dict[str, Any]], group["agents"]):
                agent["handler"] = self._handler(str(agent["pane_id"]))
        return json.dumps({"ok": True, **listed}, ensure_ascii=False)

    async def _read(self, pane_id: object) -> str:
        detail = await self.agents.get_agent({"pane_id": pane_id})
        if detail["agent"] is None:
            return _error("agent_not_found", "Herdr 中已没有这个 agent")
        return json.dumps(
            {
                "ok": True,
                "session": detail["session"],
                "agent": detail["agent"],
                "handler": detail["handler"],
                "output": str(detail["output"])[-OUTPUT_TAIL:],
                "commands": cast(list[object], detail["commands"])[-COMMAND_TAIL:],
                "can_prompt": detail["can_prompt"],
            },
            ensure_ascii=False,
        )

    async def _send(self, kwargs: dict[str, Any]) -> str:
        role_id = self.tools.get_context().get("role_id", "")
        if not role_id:
            raise PermissionError("操控 agent 需要当前角色身份")
        # Raises outside a live user-authored role tool turn: nothing is sent then.
        target = self.results.capture()
        role = self.roles.get_role(role_id)
        name = str(role.to_dict().get("name") or "") if role else ""
        source = CommandSource("role", role_id, name)
        control = self.agents.control
        if self.action == "prompt":
            command = await control.prompt(
                kwargs.get("pane_id"), kwargs.get("text"), source, target
            )
        else:
            command = await control.send_keys(
                kwargs.get("pane_id"), kwargs.get("keys"), source, target
            )
        return json.dumps(
            {"ok": True, "command": command.as_dict(), "note": _REPORT_NOTE},
            ensure_ascii=False,
        )
