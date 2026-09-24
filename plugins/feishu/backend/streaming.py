"""Live reply preview as a CardKit streaming card.

One card entity per turn: the first delta creates it (``streaming_mode``) and
sends it to the chat, later deltas replace the markdown element's full text
through the streaming text API so the client types out only the new suffix.
The final reply is written into the same card, after which streaming mode is
turned off. Updates are coalesced: per session at most one request is in
flight, requests are ``LIVE_MIN_INTERVAL_S`` apart, and a refresh loops until
the buffer stops growing, so text arriving mid-request is never lost.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable, Coroutine
from dataclasses import dataclass
from typing import Any

from .api import FeishuApi, FeishuApiError, is_rate_limited
from .formatting import (
    LIVE_ELEMENT_ID,
    closing_settings,
    live_text,
    markdown_card,
    split_markdown,
    streaming_card,
)

logger = logging.getLogger(__name__)

# The CardKit per-card cap is 10 operations/s; two per second leaves headroom
# for other cards of the app while the client-side typewriter hides the steps.
LIVE_MIN_INTERVAL_S = 0.5
LIVE_MAX_BACKOFF_S = 8.0
LIVE_MAX_FAILURES = 3
# Streaming mode was switched off by Feishu (10 minutes after it was enabled).
STREAMING_CLOSED_CODES = frozenset({200850, 300309})

# (chat_id, card content, message id to quote or None) -> sent message id
SendCard = Callable[[str, str, str | None], Awaitable[str]]


@dataclass
class _LiveCard:
    chat_id: str
    quote: str | None = None
    card_id: str = ""
    message_id: str = ""
    sequence: int = 0
    shown: str = ""
    failures: int = 0
    interval: float = LIVE_MIN_INTERVAL_S
    disabled: bool = False

    def next_sequence(self) -> int:
        self.sequence += 1
        return self.sequence


class LiveCardStreamer:
    """Owns live card state and update tasks for every session of a channel."""

    def __init__(
        self,
        api: FeishuApi,
        send_card: SendCard,
        *,
        min_interval: float = LIVE_MIN_INTERVAL_S,
    ) -> None:
        self._api = api
        self._send_card = send_card
        self._min_interval = min_interval
        self._cards: dict[str, _LiveCard] = {}
        self._buffers: dict[str, str] = {}
        self._next_at: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._tasks: dict[str, set[asyncio.Task[None]]] = {}
        self._inflight: dict[str, asyncio.Future[bool]] = {}
        self._orphans: set[asyncio.Task[None]] = set()
        self._quotes: dict[str, str] = {}

    def has_card(self, session_key: str) -> bool:
        card = self._cards.get(session_key)
        return card is not None and bool(card.message_id)

    async def begin_turn(self, session_key: str, *, quote: str | None = None) -> None:
        """Resets a session; a card left open by an unfinished turn is closed.

        ``quote`` is the user message that started the turn; the live card is
        sent as a reply to it.
        """
        await self._cancel(session_key)
        card = self._cards.get(session_key)
        self._reset(session_key)
        if quote:
            self._quotes[session_key] = quote
        if card is not None and card.message_id:
            task = asyncio.create_task(self._close_orphan(card))
            self._orphans.add(task)
            task.add_done_callback(self._orphans.discard)

    def add_delta(self, session_key: str, chat_id: str, delta: str) -> None:
        """Buffers reply text and schedules a coalesced card refresh."""
        if not delta:
            return
        self._buffers[session_key] = self._buffers.get(session_key, "") + delta
        card = self._cards.setdefault(
            session_key,
            _LiveCard(
                chat_id=chat_id,
                quote=self._quotes.get(session_key),
                interval=self._min_interval,
            ),
        )
        if card.disabled or any(
            not task.done() for task in self._tasks.get(session_key, ())
        ):
            return
        self._spawn(session_key, self._sync(session_key))

    async def finish(self, session_key: str, text: str) -> str | None:
        """Writes the final reply into the live card and ends streaming mode.

        Returns ``None`` when no live card took the reply (the caller sends it
        normally), else the part that did not fit into the card (maybe empty).
        A card whose final frame fails is recalled so the caller's fallback
        does not show the reply twice.
        """
        await self._cancel(session_key)
        card = self._cards.get(session_key)
        self._reset(session_key)
        if card is None or not card.message_id:
            return None
        chunks = split_markdown(text.strip()) if text.strip() else [card.shown]
        head, rest = chunks[0], "".join(chunks[1:])
        if head.strip() and await self._finalize(card, head):
            return rest
        await self._recall(card)
        return None

    async def close(self) -> None:
        """Cancels every refresh and waits for orphan cards to be closed."""
        for session_key in list(self._tasks):
            await self._cancel(session_key)
        if self._orphans:
            await asyncio.gather(*self._orphans, return_exceptions=True)
        self._cards.clear()
        self._quotes.clear()
        self._buffers.clear()
        self._next_at.clear()
        self._locks.clear()

    async def drain(self) -> None:
        """Waits for scheduled refreshes (tests and graceful shutdown)."""
        tasks = [task for group in self._tasks.values() for task in group]
        tasks.extend(self._orphans)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _sync(self, session_key: str) -> None:
        loop = asyncio.get_running_loop()
        while True:
            card = self._cards.get(session_key)
            if card is None or card.disabled:
                return
            if live_text(self._buffers.get(session_key, "")) == card.shown:
                return
            delay = self._next_at.get(session_key, 0.0) - loop.time()
            if delay > 0:
                await asyncio.sleep(delay)
            text = live_text(self._buffers.get(session_key, ""))
            if not text or text == card.shown:
                return
            # A request is never cancelled halfway: a card sent without its
            # message id recorded would be orphaned next to the final reply.
            push = asyncio.ensure_future(self._push(session_key, card, text))
            self._inflight[session_key] = push
            await asyncio.shield(push)
            self._next_at[session_key] = loop.time() + card.interval

    async def _push(self, session_key: str, card: _LiveCard, text: str) -> bool:
        lock = self._locks.setdefault(session_key, asyncio.Lock())
        async with lock:
            try:
                if not card.message_id:
                    await self._open(card)
                await self._api.stream_card_text(
                    card.card_id, LIVE_ELEMENT_ID, text, card.next_sequence()
                )
            except Exception as error:
                self._record_failure(session_key, card, error)
                return False
            card.shown = text
            card.failures = 0
            card.interval = self._min_interval
            return True

    async def _open(self, card: _LiveCard) -> None:
        if not card.card_id:
            card.card_id = await self._api.create_card(streaming_card())
        content = json.dumps(
            {"type": "card", "data": {"card_id": card.card_id}}, ensure_ascii=False
        )
        card.message_id = await self._send_card(card.chat_id, content, card.quote)

    def _record_failure(
        self, session_key: str, card: _LiveCard, error: Exception
    ) -> None:
        card.failures += 1
        if is_rate_limited(error) and card.failures < LIVE_MAX_FAILURES * 2:
            card.interval = min(card.interval * 2, LIVE_MAX_BACKOFF_S)
        elif card.failures >= LIVE_MAX_FAILURES or not card.message_id:
            # Without a sent card there is nothing to keep updating; the final
            # reply then goes out as a normal message.
            card.disabled = True
        logger.warning(
            "[feishu] 流式卡片刷新失败 session=%s failures=%d disabled=%s: %s",
            session_key,
            card.failures,
            card.disabled,
            error,
        )

    async def _finalize(self, card: _LiveCard, text: str) -> bool:
        try:
            await self._api.stream_card_text(
                card.card_id, LIVE_ELEMENT_ID, text, card.next_sequence()
            )
        except FeishuApiError as error:
            if error.code not in STREAMING_CLOSED_CODES:
                logger.warning("[feishu] 流式卡片收尾失败: %s", error)
                return False
            # Streaming timed out; a full update still works and ends it.
            try:
                await self._api.update_card(
                    card.card_id, markdown_card(text), card.next_sequence()
                )
            except Exception as update_error:
                logger.warning("[feishu] 流式卡片全量收尾失败: %s", update_error)
                return False
            return True
        except Exception as error:
            logger.warning("[feishu] 流式卡片收尾失败: %s", error)
            return False
        try:
            await self._api.update_card_settings(
                card.card_id, closing_settings(text), card.next_sequence()
            )
        except Exception as error:
            # The text is final; Feishu ends streaming mode itself later.
            logger.warning("[feishu] 关闭流式模式失败: %s", error)
        return True

    async def _close_orphan(self, card: _LiveCard) -> None:
        text = card.shown.strip() or "（回复已中断）"
        if not await self._finalize(card, text):
            await self._recall(card)

    async def _recall(self, card: _LiveCard) -> None:
        try:
            await self._api.delete_message(card.message_id)
        except Exception as error:
            logger.warning("[feishu] 撤回流式卡片失败: %s", error)

    def _spawn(self, session_key: str, coro: Coroutine[Any, Any, None]) -> None:
        task = asyncio.create_task(coro)
        self._tasks.setdefault(session_key, set()).add(task)

        def _done(done: asyncio.Task[None]) -> None:
            tasks = self._tasks.get(session_key)
            if tasks is not None:
                tasks.discard(done)
                if not tasks:
                    self._tasks.pop(session_key, None)
            if not done.cancelled() and done.exception() is not None:
                logger.warning("[feishu] 流式卡片任务失败: %s", done.exception())

        task.add_done_callback(_done)

    async def _cancel(self, session_key: str) -> None:
        """Stops pending refreshes but lets an in-flight request complete."""
        tasks = list(self._tasks.get(session_key, ()))
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        inflight = self._inflight.pop(session_key, None)
        if inflight is not None:
            await asyncio.gather(inflight, return_exceptions=True)

    def _reset(self, session_key: str) -> None:
        self._cards.pop(session_key, None)
        self._quotes.pop(session_key, None)
        self._buffers.pop(session_key, None)
        self._next_at.pop(session_key, None)
        self._locks.pop(session_key, None)
