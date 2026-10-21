"""Durable correlation, duplicate admission and independent reply-chain budgets."""

import hashlib
from typing import Literal

from shiori_sdk.storage import KeyValueStore

from .exchange_state import ExchangeBudget, Receipt, read_exchange_state
from .protocol import BotMessage, CallbackError

MAX_RECORDS = 512
MAX_PENDING = 16
_PENDING_STATES = {"queued", "sending", "uncertain"}


class ExchangeJournal:
    """Persist one Bot binding's receipts with a separate budget per root message."""

    def __init__(self, kv: KeyValueStore, connection_id: str, peer_id: str) -> None:
        self._kv = kv
        self._key = f"exchange:{connection_id}:{peer_id}"
        saved = kv.get(self._key, {})
        self.state = read_exchange_state(saved)
        # An interrupted remote send is uncertain and must never be replayed.
        for receipt in self.state.messages.values():
            if receipt.state == "sending":
                receipt.state = "uncertain"
                self.state.last_status = "上次发送结果不确定，请勿自动重发"
        if self.state.model_dump() != saved:
            self._save()

    def _save(self) -> None:
        self._kv.set(self._key, self.state.model_dump())

    def _make_room(self, protected_exchange: str) -> None:
        # Expire whole settled chains, never individual ancestors or counters.
        # Replies to expired chains fail instead of receiving a fresh budget.
        while len(self.state.messages) >= MAX_RECORDS:
            pending = {
                receipt.exchange_id
                for receipt in self.state.messages.values()
                if receipt.state in _PENDING_STATES
            }
            expired = next(
                (
                    exchange_id
                    for exchange_id in self.state.exchanges
                    if exchange_id != protected_exchange and exchange_id not in pending
                ),
                None,
            )
            if expired is None:
                raise CallbackError(429, "待处理交流过多，请稍后再试")
            self.state.messages = {
                key: receipt
                for key, receipt in self.state.messages.items()
                if receipt.exchange_id != expired
            }
            del self.state.exchanges[expired]

    def begin(
        self, message: BotMessage, direction: Literal["in", "out"], limit: int
    ) -> bool:
        """Reserve once in the parent's chain, or start one independent root."""
        digest = hashlib.sha256(
            (message.reply_to + "\0" + message.text).encode("utf-8")
        ).hexdigest()
        previous = self.state.messages.get(message.message_id)
        if previous is not None:
            if previous.direction != direction or previous.digest != digest:
                raise CallbackError(409, "消息标识已被其他内容使用")
            if previous.state in {"uncertain", "sending", "failed"}:
                raise CallbackError(409, "该消息结果不确定或已失败，请检查连接状态")
            return False
        exchange_id = message.message_id
        budget = ExchangeBudget()
        if message.reply_to:
            parent = self.state.messages.get(message.reply_to)
            if (
                parent is None
                or parent.direction == direction
                or parent.state == "failed"
            ):
                raise CallbackError(409, "回复对应的消息不存在或交流已结束")
            exchange_id = parent.exchange_id
            budget = self.state.exchanges[exchange_id]
            if budget.closed:
                raise CallbackError(409, "回复对应的交流已过期")
        elif exchange_id in self.state.exchanges:
            raise CallbackError(409, "消息标识已被使用或交流已过期")
        if budget.count >= limit:
            raise CallbackError(409, "已达单次交流消息上限")
        pending = sum(
            receipt.state in _PENDING_STATES
            for receipt in self.state.messages.values()
            if receipt.exchange_id == exchange_id
        )
        if pending >= MAX_PENDING:
            raise CallbackError(429, "待处理消息过多，请稍后再试")
        self._make_room(exchange_id)
        self.state.messages[message.message_id] = Receipt(
            direction=direction,
            digest=digest,
            exchange_id=exchange_id,
            reply_to=message.reply_to,
            state="queued" if direction == "in" else "sending",
            text=message.text if direction == "in" else "",
        )
        budget.count += 1
        self.state.exchanges[exchange_id] = budget
        self.state.last_status = "等待角色处理" if direction == "in" else "正在发送"
        self._save()
        return True

    def finish(
        self,
        message_id: str,
        state: Literal["accepted", "complete", "failed", "uncertain"],
        status: str,
    ) -> None:
        """Persist confirmation without retrying a potentially visible message."""
        receipt = self.state.messages[message_id]
        receipt.state = state
        receipt.text = ""
        self.state.last_status = status
        self._save()

    def complete_parent(self, message_id: str) -> None:
        """Mark a processed incoming message complete without changing its budget."""
        parent = self.state.messages.get(message_id)
        if parent is not None and parent.direction == "in":
            parent.state, parent.text = "complete", ""
            self._save()

    def pending(self) -> list[BotMessage]:
        """Replay only queued input; host history suppresses already committed turns."""
        return [
            BotMessage(key, receipt.text, receipt.reply_to)
            for key, receipt in self.state.messages.items()
            if receipt.direction == "in" and receipt.state == "queued"
        ]

    @staticmethod
    def purge_saved(kv: KeyValueStore, connection_id: str, peer_id: str) -> None:
        """Deletion must also work when the saved journal cannot be parsed."""
        kv.delete(f"exchange:{connection_id}:{peer_id}")
