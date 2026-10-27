from __future__ import annotations

import hashlib
import json
import re
import threading
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol, cast

from shiori_sdk.core.conversation import TurnStarting
from shiori_sdk.core.tools import ToolCalled
from shiori_sdk.extensions import ConfigValues
from shiori_sdk.http import HttpClient
from shiori_sdk.memory.context import MemoryPluginContext
from shiori_sdk.models import ChatProvider
from shiori_sdk.plugin_services import RuntimeLifecycle
from shiori_sdk.storage import plugin_data_dir
from shiori_sdk.tools import ToolsCapability


class _DefaultMemorySetup(MemoryPluginContext, Protocol):
    """记忆插件 setup 上下文：工具、配置、主模型、轻量模型与重载排空。"""

    @property
    def tools(self) -> ToolsCapability: ...
    @property
    def config(self) -> ConfigValues: ...
    @property
    def http(self) -> HttpClient: ...
    @property
    def light_provider(self) -> ChatProvider: ...
    @property
    def light_model(self) -> str: ...
    @property
    def runtime(self) -> RuntimeLifecycle: ...


_ITEM_LINE_RE = re.compile(r"^-\s+\[([^\]]+)\]\s*(.*)$")
_META_RE = re.compile(r"（(?P<meta>[^（）]*(?:证据|src|有印象|不确定)[^（）]*)）$")


class _DefaultMemoryRecorder:
    """记录 default 记忆引擎的检索/召回轨迹到 workspace 下的 jsonl 文件。

    两个记录入口（TurnStarting、ToolCalled 事件）共享同一份状态，因此收进
    一个小类而不是两处散落的闭包。
    """

    def __init__(self, *, data_path: Path) -> None:
        self._lock = threading.RLock()
        self._active_turns: dict[str, str] = {}
        self._data_path = data_path
        self._data_path.parent.mkdir(parents=True, exist_ok=True)

    async def record_context_prepare(self, event: TurnStarting) -> TurnStarting:
        """Records a turn's retrieved memory; the event passes unchanged.

        It joins the ``on`` chain rather than watching: the turn id it keeps is
        read by the ``recall_memory`` record of the same turn.
        """
        self._record_context_prepare(event)
        return event

    def _record_context_prepare(self, event: TurnStarting) -> None:
        turn_id = _turn_id(
            event.session_key, event.timestamp.isoformat(), event.content
        )
        self._active_turns[event.session_key] = turn_id
        block = event.retrieved_memory_block or ""
        injected_items = _items_from_block(block)
        all_hits = _hits_from_trace(event.retrieval_trace)
        self._append(
            {
                "kind": "context_prepare",
                "engine": "default",
                "turn_id": turn_id,
                "session_key": event.session_key,
                "channel": event.channel,
                "chat_id": event.chat_id,
                "user_text": event.content,
                "timestamp": event.timestamp.isoformat(),
                "created_at": _now_iso(),
                "context_prepare": {
                    "count": len(all_hits) if all_hits else len(injected_items),
                    "items": all_hits or injected_items,
                    "injected_items": injected_items,
                    "raw_block": block,
                    "retrieval_trace_raw": _jsonable(event.retrieval_trace),
                },
            }
        )

    async def record_recall_memory(self, event: ToolCalled) -> ToolCalled:
        """Records a passive turn's ``recall_memory`` result; the event passes unchanged."""
        if event.source == "passive":
            self._record_recall_memory(event)
        return event

    def _record_recall_memory(self, event: ToolCalled) -> None:
        if event.tool_name != "recall_memory":
            return
        turn_id = self._active_turns.get(event.session_key)
        if not turn_id:
            turn_id = _turn_id(
                event.session_key,
                _now_iso(),
                json.dumps(dict(event.arguments), ensure_ascii=False),
            )
        payload = _safe_json(event.result)
        raw_items: object = payload.get("items")
        items: list[dict[str, Any]] = []
        if isinstance(raw_items, list):
            items = [
                cast(dict[str, Any], raw_item)
                for raw_item in cast(list[object], raw_items)
                if isinstance(raw_item, dict)
            ]
        self._append(
            {
                "kind": "recall_memory",
                "engine": "default",
                "turn_id": turn_id,
                "session_key": event.session_key,
                "channel": event.channel,
                "chat_id": event.chat_id,
                "timestamp": _now_iso(),
                "created_at": _now_iso(),
                "recall_memory": {
                    "arguments": dict(event.arguments),
                    "status": event.status,
                    "count": len(items),
                    "items": [_compact_item(item) for item in items],
                    "raw_result": payload,
                },
            }
        )

    def _append(self, record: dict[str, Any]) -> None:
        line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
        with self._lock:
            with self._data_path.open("a", encoding="utf-8") as fh:
                _ = fh.write(line + "\n")


async def setup(ctx: _DefaultMemorySetup) -> None:
    """构造默认记忆引擎并提供 ``MEMORY_ENGINE``，再注册工具与检索记录。

    向量凭据只读插件配置。缺凭据或向量空间不一致时这里抛出，内核把插件标为
    FAILED，插座保持为空，对话仍可继续。成功则本插件就是这代的引擎，检索记录开启。

    宿主检索、plugin_undo 与总线订阅直接调用引擎，不在内核默认排空之内：重载
    排空（``on_drain``）和关库前的清理都先等这些在途调用结束（D25）。
    """
    from shiori_sdk.core.memory import MEMORY_ENGINE
    from shiori_sdk.rpc import Concurrency

    from .construct import construct_default_engine
    from .role_memory import register_role_semantic_memory
    from .tools import register_memory_meta_tools

    engine = construct_default_engine(ctx)
    ctx.runtime.on_drain(engine.wait_idle)
    ctx.provide(MEMORY_ENGINE, engine)
    register_memory_meta_tools(ctx.tools, engine)
    ctx.rpc.register(
        "roles.memory.documents",
        ctx.memory.read_documents,
        concurrency=Concurrency.READ_ONLY,
    )
    register_role_semantic_memory(ctx, engine)

    recorder = _DefaultMemoryRecorder(
        data_path=plugin_data_dir(ctx.memory.workspace, "default_memory")
        / "recall_inspector.jsonl",
    )
    ctx.on(TurnStarting, recorder.record_context_prepare)
    ctx.on(ToolCalled, recorder.record_recall_memory)


def _turn_id(session_key: str, timestamp: str, content: str) -> str:
    raw = f"{session_key}\n{timestamp}\n{content}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_json(text: str) -> dict[str, Any]:
    try:
        value: object = json.loads(text)
    except json.JSONDecodeError:
        return {"raw": text}
    return cast(dict[str, Any], value) if isinstance(value, dict) else {"raw": value}


def _items_from_block(block: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    section = ""
    for raw_line in block.splitlines():
        line = raw_line.strip()
        if line.startswith("##"):
            section = line.lstrip("#").strip()
            continue
        match = _ITEM_LINE_RE.match(line)
        if not match:
            continue
        item_id, summary = match.groups()
        items.append(
            {
                "id": item_id.strip(),
                "summary": _split_summary_meta(summary)[0],
                "tags": _split_summary_meta(summary)[1],
                "section": section,
                "injected": True,
            }
        )
    return items


def _hits_from_trace(trace: Any) -> list[dict[str, Any]]:
    hits = getattr(trace, "hits", None)
    if not isinstance(hits, list):
        return []
    items: list[dict[str, Any]] = []
    for hit in hits:
        item_id = str(getattr(hit, "item_id", "") or "")
        if not item_id:
            continue
        confidence_label = str(getattr(hit, "confidence_label", "") or "")
        tags = [confidence_label] if confidence_label else []
        items.append(
            {
                "id": item_id,
                "summary": _split_summary_meta(str(getattr(hit, "summary", "") or ""))[
                    0
                ],
                "memory_type": str(getattr(hit, "memory_type", "") or ""),
                "score": getattr(hit, "score", None),
                "injected": bool(getattr(hit, "injected", False)),
                "forced": bool(getattr(hit, "forced", False)),
                "tags": tags,
            }
        )
    return items


def _compact_item(item: dict[str, Any]) -> dict[str, Any]:
    summary, tags = _split_summary_meta(str(item.get("summary", "") or ""))
    return {
        "id": str(item.get("id", "") or ""),
        "memory_type": str(item.get("memory_type", "") or ""),
        "summary": summary,
        "tags": tags,
        "happened_at": str(item.get("happened_at", "") or ""),
        "score": item.get("score"),
        "source_ref": str(item.get("source_ref", "") or ""),
    }


def _split_summary_meta(summary: str) -> tuple[str, list[str]]:
    text = summary.strip()
    tags: list[str] = []
    while True:
        match = _META_RE.search(text)
        if match is None:
            return text, tags
        for part in match.group("meta").split("；"):
            label = part.strip()
            if label.startswith("(src:") or label.startswith("src:"):
                continue
            if label == "证据: 可回源原文":
                label = "可回源原文"
            elif label == "证据: 记忆摘要":
                label = "记忆摘要"
            if label and label not in tags:
                tags.append(label)
        text = text[: match.start()].strip()


def _jsonable(value: Any) -> Any:
    # The event freezes a top-level dict into a read-only mapping.
    if isinstance(value, Mapping):
        value = dict(cast(Mapping[object, object], value))
    try:
        _ = json.dumps(value, ensure_ascii=False)
        return value
    except TypeError:
        return repr(value)
