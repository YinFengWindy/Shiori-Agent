from __future__ import annotations

import logging
import re

from bus.events import OutboundMessage
from bus.events_lifecycle import ToolCallCompleted, ToolCallStarted, TurnStarted

from .formatting import (
    CHANNEL,
    TRACE_DEFAULT_ACTOR,
    TRACE_THINKING_LIMIT,
    _QQTraceLine,
    _QQTraceState,
    format_tool_intent,
    format_tool_target,
    format_tool_trace_lines,
    summarize_tool_result_preview,
    truncate_trace_text,
)

logger = logging.getLogger(__name__)


class _TraceMixin:
    """Collects lifecycle trace events and emits private forward-message snapshots."""

    async def _on_turn_started(self, event: TurnStarted) -> None:
        if event.channel == CHANNEL:
            self._trace_states[event.session_key] = _QQTraceState(
                user_message=event.content
            )

    async def _on_tool_call_started(self, event: ToolCallStarted) -> None:
        if event.channel != CHANNEL:
            return
        state = self._trace_states.setdefault(event.session_key, _QQTraceState())
        state.tool_lines.append(
            _QQTraceLine(
                tool_name=event.tool_name,
                intent=format_tool_intent(event.arguments),
                target=format_tool_target(event.arguments),
            )
        )

    async def _on_tool_call_completed(self, event: ToolCallCompleted) -> None:
        if event.channel != CHANNEL:
            return
        state = self._trace_states.setdefault(event.session_key, _QQTraceState())
        line = next(
            (
                item
                for item in reversed(state.tool_lines)
                if item.tool_name == event.tool_name and item.status == "started"
            ),
            None,
        )
        if line is None:
            arguments = event.final_arguments or event.arguments
            line = _QQTraceLine(
                tool_name=event.tool_name,
                intent=format_tool_intent(arguments),
                target=format_tool_target(arguments),
            )
            state.tool_lines.append(line)
        line.status = "error" if event.status == "error" else "done"
        preview = str(event.result_preview or "").strip()
        if preview:
            line.result_preview = summarize_tool_result_preview(
                event.tool_name, preview
            )

    async def _send_private_trace(
        self,
        chat_id: str,
        session_key: str,
        msg: OutboundMessage,
    ) -> None:
        api = self._api
        if api is None:
            raise RuntimeError("QQChannel 尚未启动")
        trace = self._trace_states.get(session_key)
        if trace is None:
            return
        thinking = truncate_trace_text(str(msg.thinking or ""), TRACE_THINKING_LIMIT)
        tool_text = format_tool_trace_lines(trace.tool_lines)
        if not thinking and not trace.tool_lines:
            return
        from ncatbot.core import ForwardConstructor

        info = await self._run_on_bot_loop(api.get_login_info())
        actor_name = self._trace_actor_name()
        constructor = ForwardConstructor(str(info.user_id), actor_name)
        constructor.attach_text(
            f"【模型思路】\n{thinking or '（无 thinking）'}", nickname=actor_name
        )
        constructor.attach_text(f"【工具链】\n{tool_text}", nickname=actor_name)
        forward = constructor.to_forward()
        payload = forward.to_forward_dict()
        payload["source"] = f"{actor_name} 的过程记录"
        payload["summary"] = "查看本轮过程记录"
        payload["prompt"] = f"{actor_name} 过程记录"
        payload["news"] = [
            {"text": f"{actor_name}：【模型思路】"},
            {"text": f"{actor_name}：【工具链】"},
        ]
        await self._run_on_bot_loop(
            api.send_private_forward_msg(int(chat_id), **payload)
        )

    def _trace_actor_name(self) -> str:
        cached = self._trace_actor_name_cache
        if cached:
            return cached
        if self._workspace is None:
            self._trace_actor_name_cache = TRACE_DEFAULT_ACTOR
            return TRACE_DEFAULT_ACTOR
        try:
            text = (self._workspace / "memory" / "SELF.md").read_text(encoding="utf-8")
        except Exception:
            self._trace_actor_name_cache = TRACE_DEFAULT_ACTOR
            return TRACE_DEFAULT_ACTOR
        body_match = re.search(r"(?m)^-\s*我是\s+([A-Za-z][A-Za-z0-9_-]{1,40})\b", text)
        if body_match and body_match.group(1).strip():
            self._trace_actor_name_cache = body_match.group(1).strip()
            return self._trace_actor_name_cache
        match = re.search(r"(?m)^#\s*(.+?)\s+的自我认知\s*$", text)
        if match and match.group(1).strip():
            self._trace_actor_name_cache = match.group(1).strip()
            return self._trace_actor_name_cache
        self._trace_actor_name_cache = TRACE_DEFAULT_ACTOR
        return TRACE_DEFAULT_ACTOR
