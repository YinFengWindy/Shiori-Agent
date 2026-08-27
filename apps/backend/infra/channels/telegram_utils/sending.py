"""Telegram Markdown、thinking 与主动流式发送入口。"""

import logging
from typing import Any, cast

from telegram import Bot, MessageEntity as TgEntity
from telegramify_markdown.entity import MessageEntity, split_entities

from .limiter import TelegramOutboundLimiter, _run_outbound
from .streaming import TelegramStreamMessage, _iter_stream_chunks

logger = logging.getLogger("infra.channels.telegram_utils")

def _serialize_entities(entities: list[MessageEntity]) -> list[dict] | None:
    return [entity.to_dict() for entity in entities] if entities else None


def _strip_chunk(
    text: str,
    entities: list[MessageEntity],
) -> tuple[str, list[MessageEntity]]:
    leading = len(text) - len(text.lstrip("\n"))
    trailing = len(text) - len(text.rstrip("\n"))
    if leading == 0 and trailing == 0:
        return text, entities

    end = len(text) - trailing if trailing else len(text)
    stripped = text[leading:end]
    if not stripped:
        return "", []

    stripped_utf16_len = len(stripped.encode("utf-16-le")) // 2
    adjusted: list[MessageEntity] = []
    for entity in entities:
        new_offset = entity.offset - leading
        new_end = new_offset + entity.length
        if new_end <= 0 or new_offset >= stripped_utf16_len:
            continue
        new_offset = max(0, new_offset)
        new_end = min(new_end, stripped_utf16_len)
        new_length = new_end - new_offset
        if new_length <= 0:
            continue
        adjusted.append(
            MessageEntity(
                type=entity.type,
                offset=new_offset,
                length=new_length,
                url=entity.url,
                language=entity.language,
                custom_emoji_id=entity.custom_emoji_id,
            )
        )
    return stripped, adjusted


async def send_markdown(
    bot: Bot,
    chat_id: int | str,
    text: str,
    limiter: TelegramOutboundLimiter | None = None,
) -> None:
    cid = int(chat_id)
    try:
        from . import convert_with_segments

        rendered_text, entities, _segments = convert_with_segments(text)
        chunks = split_entities(rendered_text, entities, 4090)
    except Exception as e:
        logger.warning(f"[telegram] Markdown 转换失败，降级纯文本: {e}")
        for chunk in _split_text(text, 4090):
            await _run_outbound(
                limiter,
                cid,
                kind="send",
                action=lambda: bot.send_message(chat_id=cid, text=chunk),
                label="send_message(plain)",
            )
        return
    for chunk_text, chunk_entities in chunks:
        chunk_text, chunk_entities = _strip_chunk(chunk_text, chunk_entities)
        if not chunk_text:
            continue
        await _run_outbound(
            limiter,
            cid,
            kind="send",
            action=lambda: bot.send_message(
                chat_id=cid,
                text=chunk_text,
                entities=cast(Any, _serialize_entities(chunk_entities)),
            ),
            label="send_message(markdown)",
        )


def _split_text(text: str, limit: int) -> list[str]:
    """按行切分文本，每段不超过 limit 字符。"""
    chunks, current = [], []
    current_len = 0
    for line in text.splitlines(keepends=True):
        if current_len + len(line) > limit and current:
            chunks.append("".join(current))
            current, current_len = [], 0
        # 单行本身超限时强制切断
        while len(line) > limit:
            chunks.append(line[:limit])
            line = line[limit:]
        current.append(line)
        current_len += len(line)
    if current:
        chunks.append("".join(current))
    return chunks


async def send_thinking_block(
    bot: Bot,
    chat_id: int | str,
    thinking: str,
    limiter: TelegramOutboundLimiter | None = None,
) -> None:
    """Send thinking content as expandable blockquote message(s).

    Telegram 单条消息限制 4096 UTF-16 code units。超长 thinking 按行分段，
    每段独立包裹为 expandable_blockquote。
    """
    cid = int(chat_id)
    header = "💭 思考过程\n\n"
    # 4096 UTF-16 code units, 留一点余量
    max_utf16 = 4080
    header_utf16 = len(header.encode("utf-16-le")) // 2

    chunks = _split_thinking(thinking, max_utf16 - header_utf16)
    for i, chunk in enumerate(chunks):
        text = (header if i == 0 else "") + chunk
        utf16_len = len(text.encode("utf-16-le")) // 2
        entity = TgEntity(type="expandable_blockquote", offset=0, length=utf16_len)
        try:
            await _run_outbound(
                limiter,
                cid,
                kind="send",
                action=lambda text=text, entity=entity: bot.send_message(
                    chat_id=cid,
                    text=text,
                    entities=[entity],
                ),
                label="send_message(thinking_block)",
            )
        except Exception as e:
            logger.warning("[telegram] failed to send thinking block chunk %d, skipping: %s", i, e)
            return
    logger.info("[telegram] thinking block sent, chunks=%d, length=%d", len(chunks), len(thinking))


def _split_thinking(text: str, max_utf16: int) -> list[str]:
    """按行切分 thinking 文本，每段不超过 max_utf16 个 UTF-16 code units。"""
    if len(text.encode("utf-16-le")) // 2 <= max_utf16:
        return [text]
    chunks: list[str] = []
    current_lines: list[str] = []
    current_utf16 = 0
    for line in text.splitlines(keepends=True):
        line_utf16 = len(line.encode("utf-16-le")) // 2
        if current_utf16 + line_utf16 > max_utf16 and current_lines:
            chunks.append("".join(current_lines))
            current_lines, current_utf16 = [], 0
        # 单行本身超限时强制切断
        while line_utf16 > max_utf16:
            # 按字符逼近切点
            cut = _utf16_cut(line, max_utf16)
            chunks.append(line[:cut])
            line = line[cut:]
            line_utf16 = len(line.encode("utf-16-le")) // 2
        current_lines.append(line)
        current_utf16 += line_utf16
    if current_lines:
        chunks.append("".join(current_lines))
    return chunks


def _utf16_cut(text: str, max_utf16: int) -> int:
    """返回 text 中前 max_utf16 个 UTF-16 code units 对应的 Python str 切点。"""
    utf16_count = 0
    for i, ch in enumerate(text):
        utf16_count += 2 if ord(ch) > 0xFFFF else 1
        if utf16_count > max_utf16:
            return i
    return len(text)


async def send_stream_markdown(
    bot: Bot,
    chat_id: int | str,
    text: str,
    limiter: TelegramOutboundLimiter | None = None,
) -> None:
    """主动推送场景的简化流式展示。"""
    cid = int(chat_id)
    stripped = text.strip()
    if not stripped:
        return

    if cid > 0:
        try:
            stream = TelegramStreamMessage(bot, cid, limiter)
            for chunk in _iter_stream_chunks(stripped):
                await stream.push_delta(chunk, force=True)
            await stream.finalize(text)
        except Exception as e:
            logger.warning("[telegram] stream edit 失败，降级普通发送: %s", e)
            await send_markdown(bot, cid, text, limiter)

    else:
        await send_markdown(bot, cid, text, limiter)
