from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from shiori_sdk.tools import Tool, ToolResult
from agent.tools.filesystem import EditFileTool, ReadFileTool, WriteFileTool
from agent.tools.registry import ToolRegistry
from proactive_v2.context import AgentTickContext
from proactive_v2.drift_state import DriftStateStore
from proactive_v2.outbound_text import normalize_outbound_text
from proactive_v2.reply_output import parse_push_reply, reply_properties
from session.manager.helpers import role_id_from_session_key

if TYPE_CHECKING:
    from collections.abc import Callable

    from shiori_sdk.core.proactive_host import ProactiveHost

# Host tools a drift run may call, and the risk each one is registered with.
_HOST_TOOLS = {
    "recall_memory": "read-only",
    "web_fetch": "read-only",
    "web_search": "read-only",
    "fetch_messages": "read-only",
    "search_messages": "read-only",
    "shell": "external-side-effect",
}

logger = logging.getLogger(__name__)


@dataclass
class DriftToolDeps:
    drift_dir: Path
    store: DriftStateStore
    builtin_skills_dir: Path | None = None
    memory: Any = None
    send_message_fn: Any = None
    max_web_fetch_chars: int = 8_000
    # 好感块（#714）：每轮读取，放进 context frame；未初始化时返回 None。
    affection_prompt_fn: "Callable[[], str | None] | None" = None
    proactive_host: "ProactiveHost | None" = None


class SendMessageTool(Tool):
    def __init__(
        self, ctx: AgentTickContext, send_message_fn: Any, host: ProactiveHost
    ) -> None:
        self._ctx = ctx
        self._send_message_fn = send_message_fn
        self._host = host

    @property
    def name(self) -> str:
        return "message_push"

    @property
    def description(self) -> str:
        return (
            "向用户发送一条消息，可附带图片。单次 Drift run 最多只能调用一次。\n"
            "channel 和 chat_id 在 Drift 上下文中已由配置预设，可省略不填。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "要发送的消息内容"},
                **reply_properties(
                    self._ctx.reply_context.moods if self._ctx.reply_context else ()
                ),
                "image": {
                    "type": "string",
                    "description": "要发送的一张图片本地路径或 URL",
                },
                "media": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "要随消息发送的图片路径或 URL 列表",
                },
                "channel": {
                    "type": "string",
                    "description": "目标渠道（Drift 上下文可省略，已由配置预设）",
                },
                "chat_id": {
                    "type": "string",
                    "description": "目标会话 ID（Drift 上下文可省略，已由配置预设）",
                },
            },
            "required": ["mood", "thought"],
        }

    async def execute(
        self,
        message: str = "",
        messages: list[str] | None = None,
        content: str = "",
        image: str = "",
        media: list[str] | str | None = None,
        mood: str = "",
        thought: str = "",
        **_: Any,
    ) -> str:
        text = normalize_outbound_text(message or content or "").strip()
        media_paths = self._normalize_media(image=image, media=media)
        if self._send_message_fn is None:
            logger.info("[drift_tools] message_push unavailable")
            return json.dumps(
                {"error": "message_push not configured"}, ensure_ascii=False
            )
        if self._ctx.drift_message_attempted:
            logger.info("[drift_tools] message_push rejected: already used")
            return json.dumps(
                {"error": "message_push already used in this drift run"},
                ensure_ascii=False,
            )
        if messages is None and not text and not media_paths:
            logger.info("[drift_tools] message_push rejected: empty message and media")
            return json.dumps(
                {"error": "message or media is required"}, ensure_ascii=False
            )
        reply = parse_push_reply(
            {
                "message": text,
                "messages": messages,
                "media": media_paths,
                "mood": mood,
                "thought": thought,
            },
            self._ctx,
            self._host,
        )
        self._ctx.drift_message_attempted = True
        ok = await self._send_message_fn(reply, media_paths, self._ctx.reply_context)
        if not ok:
            logger.warning("[drift_tools] message_push failed")
            return json.dumps({"error": "message_push failed"}, ensure_ascii=False)
        self._ctx.drift_message_sent = True
        self._ctx.role_reply = reply
        logger.info("[drift_tools] message_push ok")
        return json.dumps({"ok": True}, ensure_ascii=False)

    @staticmethod
    def _normalize_media(
        *, image: str = "", media: list[str] | str | None = None
    ) -> list[str]:
        paths: list[str] = []
        if image:
            paths.append(str(image).strip())
        if isinstance(media, str):
            paths.append(media.strip())
        elif media:
            paths.extend(str(item).strip() for item in media)
        return [path for path in paths if path]


class FinishDriftTool(Tool):
    def __init__(
        self,
        ctx: AgentTickContext,
        store: DriftStateStore,
    ) -> None:
        self._ctx = ctx
        self._store = store

    @property
    def name(self) -> str:
        return "finish_drift"

    @property
    def description(self) -> str:
        return "【终止工具】结束本次 Drift，保存进度状态。调用后 loop 立即结束。"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "skill_used": {"type": "string"},
                "one_line": {"type": "string"},
                "next": {"type": "string"},
                "message_result": {
                    "type": "string",
                    "enum": ["sent", "silent"],
                    "description": (
                        "sent 表示本轮已经成功调用 message_push；"
                        "silent 表示本轮确认不该打扰用户，静默结束。"
                    ),
                },
                "note": {"type": "string"},
            },
            "required": ["skill_used", "one_line", "next", "message_result"],
        }

    async def execute(
        self,
        skill_used: str,
        one_line: str,
        next: str,
        message_result: str = "",
        note: str | None = None,
        **_: Any,
    ) -> str:
        skill_name = str(skill_used or "").strip()
        if skill_name not in self._store.valid_skill_names():
            logger.info(
                "[drift_tools] finish_drift rejected unknown skill=%s", skill_name
            )
            return json.dumps(
                {"error": f"unknown skill: {skill_name}"},
                ensure_ascii=False,
            )
        summary = str(one_line or "").strip()
        next_action = str(next or "").strip()
        if not summary:
            return json.dumps({"error": "one_line is required"}, ensure_ascii=False)
        if not next_action:
            return json.dumps({"error": "next is required"}, ensure_ascii=False)
        message_result_value = str(message_result or "").strip()
        if message_result_value not in {"sent", "silent"}:
            return json.dumps(
                {"error": "message_result must be one of: sent, silent"},
                ensure_ascii=False,
            )
        if message_result_value == "sent" and not self._ctx.drift_message_sent:
            return json.dumps(
                {"error": "message_result=sent requires successful message_push first"},
                ensure_ascii=False,
            )
        if message_result_value == "silent" and self._ctx.drift_message_sent:
            return json.dumps(
                {
                    "error": "message_result=silent conflicts with successful message_push"
                },
                ensure_ascii=False,
            )
        note_text = str(note).strip() if note is not None else None
        self._store.save_finish(
            skill_used=skill_name,
            one_line=summary,
            next_action=next_action,
            message_result=message_result_value,
            note=note_text,
            now_utc=self._ctx.now_utc,
        )
        self._ctx.drift_finished = True
        logger.info(
            "[drift_tools] finish_drift ok: skill=%s one_line=%s next=%s",
            skill_name,
            summary[:120],
            next_action[:100],
        )
        return json.dumps({"ok": True}, ensure_ascii=False)


class MountServerTool(Tool):
    """挂载一个已连接的 MCP server，使其工具在本次 drift 中可用。"""

    def __init__(self, host: ProactiveHost, mounted: set[str]) -> None:
        self._host = host
        self._mounted = mounted

    @property
    def name(self) -> str:
        return "mount_server"

    @property
    def description(self) -> str:
        return (
            "挂载一个已连接的 MCP server，使其工具在本次 drift 中可用。"
            "挂载后即可直接调用该 server 的工具。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "server": {
                    "type": "string",
                    "description": "要挂载的 MCP server 名称",
                },
            },
            "required": ["server"],
        }

    async def execute(self, server: str, **_: Any) -> str:
        server = str(server or "").strip()
        if not server:
            return json.dumps({"error": "server is required"}, ensure_ascii=False)
        names = set(self._host.mcp_tool_names(server))
        if not names:
            return json.dumps(
                {"error": f"MCP server '{server}' 不存在或未连接"},
                ensure_ascii=False,
            )
        new = names - self._mounted
        if not new:
            return json.dumps(
                {
                    "ok": True,
                    "message": f"'{server}' 已挂载，无新增工具",
                    "tools": sorted(names),
                },
                ensure_ascii=False,
            )
        self._mounted |= new
        logger.info(
            "[drift_tools] mount_server ok: server=%s new=%s", server, sorted(new)
        )
        return json.dumps(
            {"ok": True, "tools": sorted(names), "new": sorted(new)},
            ensure_ascii=False,
        )


class DriftWebFetchTool(Tool):
    def __init__(self, wrapped: Tool, max_chars: int) -> None:
        self._wrapped = wrapped
        self._max_chars = max(1, int(max_chars))

    @property
    def name(self) -> str:
        return self._wrapped.name

    @property
    def description(self) -> str:
        return self._wrapped.description

    @property
    def parameters(self) -> dict[str, Any]:
        return self._wrapped.parameters

    async def execute(self, **kwargs: Any) -> str | ToolResult:
        result = await self._wrapped.execute(**kwargs)
        if not isinstance(result, str):
            return result
        try:
            payload = json.loads(result)
        except Exception:
            return result
        text = payload.get("text")
        if not isinstance(text, str) or len(text) <= self._max_chars:
            return result
        payload["text"] = text[: self._max_chars]
        payload["length"] = len(payload["text"])
        payload["truncated"] = True
        payload["note"] = (
            f"内容已截断至 {self._max_chars} 字符，"
            "如需更多内容请缩小范围或改用更精确的读取方式"
        )
        return json.dumps(payload, ensure_ascii=False)


class HostTool(Tool):
    """One host tool, run through ``PROACTIVE_HOST`` in the role's user context.

    The host gives memory and message tools the role's identity, so recall
    searches the role and message lookups see only its user-context threads.
    """

    def __init__(
        self, host: ProactiveHost, schema: Mapping[str, Any], role_id: str
    ) -> None:
        function = schema["function"]
        self._host = host
        self._name = str(function["name"])
        self._description = str(function.get("description") or "")
        self._parameters = dict(function.get("parameters") or {})
        self._role_id = role_id

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def parameters(self) -> dict[str, Any]:
        return self._parameters

    async def execute(self, **kwargs: Any) -> str | ToolResult:
        return await self._host.run_host_tool(self._name, kwargs, role_id=self._role_id)


class DriftReadFileTool(Tool):
    def __init__(self, drift_dir: Path, builtin_skills_dir: Path | None = None) -> None:
        self._drift_dir = drift_dir
        self._builtin_skills_dir = builtin_skills_dir
        self._relative_reader = ReadFileTool(allowed_dir=drift_dir)
        self._absolute_reader = ReadFileTool()

    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return self._absolute_reader.description

    @property
    def parameters(self) -> dict[str, Any]:
        return self._absolute_reader.parameters

    async def execute(self, path: str, **kwargs: Any) -> Any:
        raw = str(path or "").strip()
        if not raw:
            return await self._absolute_reader.execute(path=path, **kwargs)
        raw_path = Path(raw).expanduser()
        if raw_path.is_absolute():
            return await self._absolute_reader.execute(path=path, **kwargs)
        if raw.startswith("skills/") and self._builtin_skills_dir is not None:
            builtin_path = self._builtin_skills_dir / raw.removeprefix("skills/")
            if builtin_path.exists():
                return await self._absolute_reader.execute(
                    path=str(builtin_path), **kwargs
                )
        reader = self._relative_reader
        return await reader.execute(path=path, **kwargs)


def build_drift_tool_registry(
    *,
    ctx: AgentTickContext,
    deps: DriftToolDeps,
    mounted_tool_names: set[str] | None = None,
    mcp_servers: set[str] | None = None,
) -> ToolRegistry:
    tools = ToolRegistry()
    drift_dir = deps.drift_dir
    tools.register(
        DriftReadFileTool(drift_dir, deps.builtin_skills_dir),
        risk="read-only",
    )
    tools.register(WriteFileTool(allowed_dir=drift_dir), risk="write")
    tools.register(EditFileTool(allowed_dir=drift_dir), risk="write")

    host = deps.proactive_host
    if host is None:
        raise RuntimeError("发呆回合缺少宿主端口")
    role_id = role_id_from_session_key(ctx.session_key)
    if not role_id:
        raise ValueError(f"发呆回合只服务角色会话: {ctx.session_key}")
    # Only the host tools the generation has registered, in this order.
    for schema in host.tool_schemas(tuple(_HOST_TOOLS)):
        tool: Tool = HostTool(host, schema, role_id)
        if tool.name == "web_fetch":
            tool = DriftWebFetchTool(tool, deps.max_web_fetch_chars)
        tools.register(tool, risk=_HOST_TOOLS[tool.name])

    # mount_server: 只有宿主报告已连接的 MCP 服务时才注册
    if mcp_servers:
        mounted = mounted_tool_names if mounted_tool_names is not None else set()
        tools.register(MountServerTool(host, mounted), risk="read-only")

    tools.register(
        SendMessageTool(ctx, deps.send_message_fn, host),
        risk="external-side-effect",
    )
    tools.register(FinishDriftTool(ctx, deps.store), risk="write")
    return tools
