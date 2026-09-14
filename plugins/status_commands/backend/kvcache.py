"""KVCache command consuming observe's optional public telemetry API."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

from agent.lifecycle.commands import abort_command, normalize_command
from agent.plugin_host.dependencies import PluginDependencies
from agent.prompting import is_context_frame

from .formatting import content_to_text, preview_text

if TYPE_CHECKING:
    from agent.lifecycle.phases.before_turn import BeforeTurnFrame
    from agent.lifecycle.types import TurnState

    KVCacheTurn = Any
    ObserveTelemetry = Any

logger = logging.getLogger("plugin.status_commands")
_SESSION_SLOT = "session:session"
_CTX_SLOT = "session:ctx"
_TS_PATTERN = re.compile(r"(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})")
_BEIJING_TZ = ZoneInfo("Asia/Shanghai")


class KVCacheCommandModule:
    """Read telemetry on demand without requiring observe to be installed."""

    slot = "status_commands.kvcache"
    requires = ("before_turn.acquire_session", _SESSION_SLOT)
    produces = (_CTX_SLOT,)

    def __init__(self, dependencies: PluginDependencies) -> None:
        self._dependencies = dependencies

    async def run(self, frame: BeforeTurnFrame):
        """Handle cache commands before retrieval, keeping prior aborts intact."""
        if _CTX_SLOT in frame.slots:
            return frame
        state = frame.input
        command = normalize_command(state.msg.content)
        if command not in {"/kvcache", "/cache_status"}:
            return frame
        logger.info("[status_commands:%s] 命中命令: %s", type(self).__name__, command)
        frame.slots[_CTX_SLOT] = abort_command(state, self._build_reply(state))
        return frame

    def _build_reply(self, state: TurnState) -> str:
        # Re-resolve each command so provider unload/reload cannot retain a stale API.
        reader: ObserveTelemetry | None = self._dependencies.get_optional("observe")
        if reader is None:
            return "KVCache 不可用（observe 未安装、未启用或未提供遥测接口）。"
        args = state.msg.content.strip().split()
        limit = 5
        if len(args) > 1:
            try:
                limit = max(1, min(30, int(args[1])))
            except ValueError:
                pass
        try:
            turns = reader.recent_cache_turns(state.session_key, limit=limit)
        except OSError:
            # This command is the user-facing boundary for storage read failures.
            logger.exception("KVCache 查询失败")
            return "KVCache 查询失败。"
        return _format_cache_status(turns)


def _format_cache_status(turns: tuple[KVCacheTurn, ...]) -> str:
    if not turns:
        return "暂无 KVCache 数据。"
    overall_prompt = sum(turn.prompt_tokens or 0 for turn in turns)
    overall_hit = sum(turn.hit_tokens or 0 for turn in turns)
    overall_pct = (overall_hit / overall_prompt * 100) if overall_prompt > 0 else 0.0
    lines = [
        f"⚡ KVCache · 最近 {len(turns)} 轮",
        "",
        f"命中率  {overall_pct:.1f}%  {_pct_bar(overall_pct)}",
        f"Token  {overall_hit:,} / {overall_prompt:,}",
    ]
    for turn in turns:
        content = content_to_text(turn.reply)
        if is_context_frame(content):
            content = ""
        preview = preview_text(content, limit=72)
        hit, prompt = turn.hit_tokens or 0, turn.prompt_tokens or 0
        pct = (hit / prompt * 100) if prompt > 0 else 0.0
        lines.extend(["", ""])
        lines.append(
            f"{_format_ts(turn.timestamp)}   {_pct_emoji(pct)} {pct:.1f}%  {_pct_bar(pct)}"
        )
        lines.append(f"    {hit:,} / {prompt:,} tokens")
        if preview:
            lines.append(f"    {preview}")
    return "\n".join(lines)


def _format_ts(ts: str) -> str:
    try:
        parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(_BEIJING_TZ)
        return f"{parsed.month}-{parsed.day} {parsed.hour:02d}:{parsed.minute:02d}"
    except ValueError:
        pass
    m = _TS_PATTERN.search(ts)
    if m:
        return f"{int(m.group(2))}-{int(m.group(3))} {m.group(4)}:{m.group(5)}"
    return ts


def _pct_bar(pct: float, width: int = 10) -> str:
    filled = round(pct / 100 * width)
    filled = max(0, min(width, filled))
    return "█" * filled + "░" * (width - filled)


def _pct_emoji(pct: float) -> str:
    if pct >= 80:
        return "🟢"
    if pct >= 40:
        return "🟡"
    return "🔴"
