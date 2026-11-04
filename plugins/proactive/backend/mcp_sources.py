"""
proactive/mcp_sources.py — 从 MCP server 拉取 ProactiveEvent 的通用客户端。

读取 ~/.shiori/workspace/proactive_sources.json 中的配置，
动态调用各 MCP server 的 get_tool / ack_tool。

连接和凭据只由 mcp 插件管理；此模块只解析主动信息源的业务结果。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from shiori_sdk.extensions import Dependencies
from shiori_sdk.tools import ToolResult

logger = logging.getLogger(__name__)

_POLL_TOOL_TIMEOUT = 180.0


class ContextSourceFormatError(ValueError):
    """context MCP 源返回不符合 dict/list[dict] 契约时抛出的格式错误。"""

    def __init__(self, server: str, payload_type: str) -> None:
        self.server = server
        self.payload_type = payload_type
        super().__init__(
            f"context source {server!r} returned unsupported payload type "
            f"{payload_type}; expected dict or list[dict]"
        )


# ---------------------------------------------------------------------------
# Config loaders
# ---------------------------------------------------------------------------


def _load_sources(workspace: Path) -> list[dict]:
    path = workspace / "proactive_sources.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [s for s in data.get("sources", []) if s.get("enabled", True)]
    except FileNotFoundError:
        return []
    except Exception as e:
        logger.warning("[mcp_sources] proactive_sources.json 读取失败: %s", e)
        return []


class McpClientPool:
    """Source adapter over the MCP owner's current export; owns no sessions."""

    def __init__(
        self,
        workspace: Path | None = None,
        *,
        dependencies: Callable[[], Dependencies | None] = lambda: None,
    ):
        self._workspace = workspace
        self._dependencies = dependencies

    async def call(
        self,
        server: str,
        tool_name: str,
        args: dict[str, Any],
        *,
        timeout: float | None = None,
        retry_on_transport: bool = False,
    ) -> Any:
        """Resolve on every call so disable/reload cannot retain an old export."""
        dependencies = self._dependencies()
        api = dependencies.get_optional("mcp") if dependencies else None
        if api is None:
            raise RuntimeError("MCP 插件未启用")
        # Import only after the optional provider exists; no mandatory install.
        from plugins.mcp.backend.api import McpAPI

        if not isinstance(api, McpAPI):
            raise TypeError("MCP 插件未提供调用接口")
        raw = await api.call(
            server,
            tool_name,
            args,
            timeout=timeout,
            retry_on_transport=retry_on_transport,
        )
        return _decode_result(raw)


def _decode_result(raw: str | ToolResult) -> Any:
    if isinstance(raw, ToolResult):
        if raw.content_blocks:
            raise ValueError(
                "Proactive MCP sources require text results; images are unsupported"
            )
        if raw.structured_content is not None:
            return raw.structured_content
        raw = raw.text
    if raw and raw.strip().startswith(("[", "{")):
        return json.loads(raw)
    return raw


# ── Async pool-based variants ─────────────────────────────────────────────────


async def fetch_alert_events_async(pool: McpClientPool) -> list[dict]:
    return await _fetch_by_channel_async(pool, channel="alert")


async def fetch_content_events_async(pool: McpClientPool) -> list[dict]:
    return await _fetch_by_channel_async(pool, channel="content")


async def fetch_context_data_async(pool: McpClientPool) -> list[dict]:
    return await _fetch_by_channel_async(pool, channel="context")


def _extract_proactive_events(data: Any, *, server: str, kind: str) -> list[dict]:
    # 1. proactive 事件源约定返回 list[dict]。
    # 2. 这里只保留 kind 匹配当前 channel 的事件，并补上 ack_server。
    if not isinstance(data, list):
        return []
    result: list[dict] = []
    for event in data:
        if not isinstance(event, dict) or event.get("kind") != kind:
            continue
        enriched = dict(event)
        enriched.setdefault("ack_server", server)
        result.append(enriched)
    return result


def _extract_context_items(data: Any, *, server: str) -> list[dict]:
    # context 源兼容两种返回形态：
    # 1. 单个 dict：包装成长度为 1 的列表
    # 2. list[dict]：逐条补 _source 后原样返回
    if isinstance(data, dict):
        item = dict(data)
        item.setdefault("_source", server)
        return [item]
    if isinstance(data, list):
        result: list[dict] = []
        invalid_count = 0
        for item in data:
            if not isinstance(item, dict):
                invalid_count += 1
                continue
            enriched = dict(item)
            enriched.setdefault("_source", server)
            result.append(enriched)
        if invalid_count:
            logger.warning(
                "[mcp_sources] context 源 %s 返回 list 中有 %d 个非法条目，已跳过",
                server,
                invalid_count,
            )
        return result
    raise ContextSourceFormatError(server, type(data).__name__)


async def _fetch_by_channel_async(pool: McpClientPool, *, channel: str) -> list[dict]:
    result: list[dict] = []
    # 1. 先按 channel 从 proactive_sources.json 中挑出本轮该访问的源。
    for src in _iter_sources_by_channel(channel, pool._workspace):
        server = src.get("server", "")
        # 2. 每个源默认调用：
        #    - context 走 get_context
        #    - alert/content 走 get_proactive_events
        #    也允许在配置里用 get_tool 覆盖。
        get_tool = src.get(
            "get_tool",
            "get_context" if channel == "context" else "get_proactive_events",
        )
        try:
            # 3. 通过 MCP 插件当前导出调用允许的工具。
            #    MCP owner 负责准入及明确允许的单次重试；此处只解析业务 JSON。
            data = await pool.call(
                server,
                get_tool,
                {},
                retry_on_transport=True,
            )
            if channel == "context":
                # 4a. context 通道不看 kind，直接把返回值规范成 list[dict]。
                items = _extract_context_items(data, server=server)
                result.extend(items)
                logger.debug(
                    "[mcp_sources] context 源 %s 返回 %d 条", server, len(items)
                )
            else:
                # 4b. alert/content 通道要求远端返回 proactive event 列表，
                #     再按 kind 过滤出当前通道的事件。
                events = _extract_proactive_events(data, server=server, kind=channel)
                result.extend(events)
                logger.debug(
                    "[mcp_sources] %s 返回 %d 条 %s 事件", server, len(events), channel
                )
        except Exception as e:
            # 5. 单个源失败只记日志，不阻断其他源。
            logger.warning(
                "[mcp_sources] fetch_%s %s.%s failed: %s",
                channel,
                server,
                get_tool,
                e,
            )
    return result


def _iter_sources_by_channel(channel: str, workspace: Path | None = None) -> list[dict]:
    if workspace is None:
        return []
    sources = _load_sources(workspace)
    result: list[dict] = []
    # 根据 channel 做一层静态路由：
    # - context 只取 channel=context 的源
    # - alert 排除纯 content 源
    # - content 排除纯 alert 源
    for src in sources:
        src_channel = str(src.get("channel", "")).strip().lower()
        if channel == "context":
            if src_channel == "context":
                result.append(src)
            continue
        if src_channel in ("context",):
            continue
        if channel == "alert" and src_channel in ("content",):
            continue
        if channel == "content" and src_channel in ("alert",):
            continue
        result.append(src)
    return result


def _build_ack_map(sources: list[dict]) -> dict[str, tuple[str, list[str]]]:
    ack_map: dict[str, tuple[str, list[str]]] = {}
    for src in sources:
        ack_tool = src.get("ack_tool")
        if ack_tool:
            ack_map[src["server"]] = (ack_tool, [])
    return ack_map


async def poll_content_feeds_async(pool: McpClientPool) -> None:
    failed_servers: list[str] = []
    for src in _iter_sources_by_channel("content", pool._workspace):
        poll_tool = src.get("poll_tool")
        if not poll_tool:
            continue
        server = src.get("server", "")
        try:
            result = await pool.call(server, poll_tool, {}, timeout=_POLL_TOOL_TIMEOUT)
            if isinstance(result, str) and result.startswith("error:"):
                raise RuntimeError(f"poll_feeds 系统级失败: {result}")
            logger.info(
                "[mcp_sources] poll_content_feeds: %s.%s 完成", server, poll_tool
            )
        except Exception as e:
            logger.warning(
                "[mcp_sources] poll_content_feeds: %s.%s 失败: %s",
                server,
                poll_tool,
                e,
                exc_info=True,
            )
            failed_servers.append(server)
    if failed_servers:
        raise RuntimeError(f"poll_content_feeds 以下源失败: {failed_servers}")


async def acknowledge_events_async(pool: McpClientPool, events: list) -> None:
    workspace = pool._workspace
    if workspace is None:
        return
    ack_map = _build_ack_map(_load_sources(workspace))
    for e in events:
        ack_server: str = getattr(e, "_ack_server", None) or ""
        if not ack_server:
            ack_server = getattr(e, "source_name", "") or ""
        ack_id: str | None = getattr(e, "ack_id", None)
        if ack_server in ack_map and ack_id:
            ack_map[ack_server][1].append(ack_id)
    for server, (ack_tool, ids) in ack_map.items():
        if not ids:
            continue
        try:
            await pool.call(server, ack_tool, {"event_ids": ids})
            logger.info(
                "[mcp_sources] acked %d 事件 via %s.%s ids=%s",
                len(ids),
                server,
                ack_tool,
                ids,
            )
        except Exception as e:
            logger.warning("[mcp_sources] ack failed %s.%s: %s", server, ack_tool, e)


async def acknowledge_content_entries_async(
    pool: McpClientPool,
    entries: list[tuple[str, str]],
    ttl_hours: int | None = None,
) -> None:
    if not entries:
        return
    workspace = pool._workspace
    if workspace is None:
        return
    ack_map = _build_ack_map(_load_sources(workspace))
    for source_key, item_id in entries:
        if not source_key.startswith("mcp:"):
            continue
        parts = source_key.split(":", 2)
        server = parts[1] if len(parts) >= 2 else ""
        ack_id = parts[2] if len(parts) >= 3 else item_id
        if server in ack_map and ack_id:
            ack_map[server][1].append(ack_id)
    for server, (ack_tool, ids) in ack_map.items():
        if not ids:
            continue
        args: dict = {"event_ids": ids}
        if ttl_hours is not None and ttl_hours > 0:
            args["ttl_hours"] = ttl_hours
        try:
            await pool.call(server, ack_tool, args)
        except Exception as e:
            logger.warning(
                "[mcp_sources] content ack failed %s.%s: %s", server, ack_tool, e
            )
