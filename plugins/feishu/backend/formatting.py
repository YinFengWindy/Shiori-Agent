"""Feishu message payload parsing, card building, and channel-facing text."""

from __future__ import annotations

import json
from typing import Any, cast

CHANNEL = "feishu"
FEISHU_DOMAIN = "https://open.feishu.cn"
LARK_DOMAIN = "https://open.larksuite.com"
DOMAINS = {"feishu": FEISHU_DOMAIN, "lark": LARK_DOMAIN}

# Keeps one card well under the 30 KB card limit even for CJK text (3 B/char)
# plus card JSON overhead; longer replies continue in follow-up cards.
CARD_TEXT_LIMIT = 4000
LIVE_ELEMENT_ID = "reply_md"
LIVE_PLACEHOLDER = "…"
SUMMARY_LIMIT = 60

SYSTEM_PROMPT_HINT = (
    "## 飞书渠道渲染限制"
    "\n- 回复显示在飞书消息卡片里，只支持常用 Markdown：标题、粗体、斜体、删除线、"
    "列表、代码块、表格和链接；不支持 HTML，也不能用 Markdown 语法内嵌图片。"
    "\n- 图片和文件请用 `message_push` 的 image / file 参数单独发送。"
    f"\n- 单张卡片约 {CARD_TEXT_LIMIT} 字，超出会拆成多条消息，回复尽量精炼。"
    "\n- 主动给当前用户发消息时用 `message_push` 的 `channel=feishu`，"
    "chat_id 保持为当前私聊的 `oc_…`。"
)
PUSH_TARGET_HINT = (
    "飞书私聊，chat_id 为 oc_… 私聊会话 ID，也可直接填用户 open_id（ou_…）"
)


def as_dict(value: object) -> dict[str, Any]:
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def as_list(value: object) -> list[Any]:
    return cast(list[Any], value) if isinstance(value, list) else []


def load_json_object(raw: str) -> dict[str, Any]:
    """Parses a Feishu ``content`` string; malformed payloads yield ``{}``."""
    try:
        return as_dict(json.loads(raw or ""))
    except (TypeError, ValueError):
        return {}


def extract_text(content: dict[str, Any], mentions: list[Any] | None = None) -> str:
    """Returns the text of a ``text`` message with ``@_user_N`` keys resolved."""
    text = str(content.get("text") or "")
    for mention in mentions or []:
        item = as_dict(mention)
        key = str(item.get("key") or "")
        if key:
            name = str(item.get("name") or "").strip()
            text = text.replace(key, f"@{name}" if name else "")
    return text.strip()


def extract_post(content: dict[str, Any]) -> tuple[str, list[str]]:
    """Flattens a ``post`` rich-text message into text plus embedded image keys.

    Received posts carry ``title``/``content`` at the top level; posts fetched
    through the message API may still be wrapped in a locale key (``zh_cn``).
    """
    body = content
    if "content" not in body:
        body = next(
            (as_dict(value) for value in body.values() if "content" in as_dict(value)),
            {},
        )
    lines: list[str] = []
    images: list[str] = []
    title = str(body.get("title") or "").strip()
    if title:
        lines.append(title)
    for paragraph in as_list(body.get("content")):
        parts: list[str] = []
        for segment in as_list(paragraph):
            item = as_dict(segment)
            tag = str(item.get("tag") or "")
            if tag in {"text", "md"}:
                parts.append(str(item.get("text") or ""))
            elif tag == "a":
                parts.append(str(item.get("text") or item.get("href") or ""))
            elif tag == "at":
                parts.append("@" + str(item.get("user_name") or ""))
            elif tag == "code_block":
                parts.append(str(item.get("text") or ""))
            elif tag == "img" and item.get("image_key"):
                images.append(str(item["image_key"]))
        line = "".join(parts).strip()
        if line:
            lines.append(line)
    return "\n".join(lines).strip(), images


def extract_card_text(content: dict[str, Any]) -> str:
    """Collects the visible strings of a card fetched from the message API.

    The rendered card body differs between card schemas, so this walks the
    structure and keeps ``title``/``text``/``content`` strings in order.
    """
    parts: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for key, value in cast(dict[str, Any], node).items():
                if key in {"title", "text", "content"} and isinstance(value, str):
                    if value.strip():
                        parts.append(value.strip())
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in cast(list[Any], node):
                walk(item)

    walk(content)
    return "\n".join(parts).strip()


def split_markdown(text: str, limit: int = CARD_TEXT_LIMIT) -> list[str]:
    """Splits text on line boundaries so no chunk exceeds ``limit`` characters."""
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    current = ""
    for line in text.splitlines(keepends=True):
        if current and len(current) + len(line) > limit:
            chunks.append(current)
            current = ""
        while len(line) > limit:
            chunks.append(line[:limit])
            line = line[limit:]
        current += line
    if current:
        chunks.append(current)
    return chunks


def summary_of(text: str) -> str:
    """Returns the chat-list preview text for a card."""
    flat = " ".join(text.split())
    if len(flat) <= SUMMARY_LIMIT:
        return flat
    return flat[: SUMMARY_LIMIT - 1] + "…"


def markdown_card(text: str) -> str:
    """Builds a static JSON 2.0 card that renders ``text`` as Markdown."""
    return json.dumps(
        {
            "schema": "2.0",
            "config": {
                "update_multi": True,
                "summary": {"content": summary_of(text)},
            },
            "body": {"elements": [{"tag": "markdown", "content": text}]},
        },
        ensure_ascii=False,
    )


def streaming_card() -> str:
    """Builds the CardKit entity used for a live reply, in streaming mode.

    ``update_multi`` must stay true for streaming updates; the element id is
    what the streaming text API addresses.
    """
    return json.dumps(
        {
            "schema": "2.0",
            "config": {
                "update_multi": True,
                "streaming_mode": True,
                "summary": {"content": ""},
                "streaming_config": {
                    "print_frequency_ms": {"default": 50},
                    "print_step": {"default": 2},
                    "print_strategy": "fast",
                },
            },
            "body": {
                "elements": [
                    {
                        "tag": "markdown",
                        "content": LIVE_PLACEHOLDER,
                        "element_id": LIVE_ELEMENT_ID,
                    }
                ]
            },
        },
        ensure_ascii=False,
    )


def closing_settings(text: str) -> str:
    """Card settings that end streaming mode and show the reply in chat lists."""
    return json.dumps(
        {
            "config": {
                "streaming_mode": False,
                "summary": {"content": summary_of(text)},
            }
        },
        ensure_ascii=False,
    )


def live_text(reply: str) -> str:
    """Returns what the live card shows for the reply buffered so far.

    The preview keeps the head of the reply (not the tail) so each update
    extends the previous one and the client can animate only the new part.
    """
    text = reply.strip()
    if len(text) <= CARD_TEXT_LIMIT:
        return text
    return text[: CARD_TEXT_LIMIT - 1] + "…"
