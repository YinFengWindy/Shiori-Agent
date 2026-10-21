"""Durable correlation, duplicate admission and bounded automatic exchanges."""

import hashlib
import time
from collections.abc import Callable
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from shiori_sdk.storage import KeyValueStore

from .protocol import BotMessage, CallbackError

QUIET_RESET_SECONDS = 1800
MAX_RECORDS = 512
MAX_PENDING = 16


class Receipt(BaseModel):
    """Transport state without a second copy of completed conversation text."""

    model_config = ConfigDict(extra="forbid", strict=True)
    direction: Literal["in", "out"]
    digest: str
    exchange_id: str
    reply_to: str = ""
    state: Literal["queued", "sending", "accepted", "complete", "failed", "uncertain"]
    text: str = ""


class ExchangeState(BaseModel):
    """A message budget survives new IDs, reconnects and application restarts."""

    model_config = ConfigDict(extra="forbid", strict=True)
    exchange_id: str = ""
    count: int = Field(default=0, ge=0)
    last_activity: float = 0.0
    messages: dict[str, Receipt] = Field(default_factory=dict)
    last_status: str = ""


class ExchangeJournal:
    """Persist one Bot binding's correlation and enforce its admission budget."""

    def __init__(
        self,
        kv: KeyValueStore,
        connection_id: str,
        peer_id: str,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._kv = kv
        self._key = f"exchange:{connection_id}:{peer_id}"
        self._clock = clock
        try:
            self.state = ExchangeState.model_validate(kv.get(self._key, {}))
        except ValidationError:
            raise ValueError("Grok 对话状态无效，不能安全恢复") from None
        # A process exit may leave an accepted remote send without its receipt.
        # Keep it uncertain; startup must never replay that side effect.
        changed = False
        for receipt in self.state.messages.values():
            if receipt.state == "sending":
                receipt.state = "uncertain"
                changed = True
        if changed:
            self._save()

    def _save(self) -> None:
        while len(self.state.messages) > MAX_RECORDS:
            key = next(
                (
                    key
                    for key, receipt in self.state.messages.items()
                    if receipt.state not in {"queued", "sending"}
                    and receipt.exchange_id != self.state.exchange_id
                ),
                None,
            )
            if key is None:
                break
            del self.state.messages[key]
        self._kv.set(self._key, self.state.model_dump())

    def begin(
        self, message: BotMessage, direction: Literal["in", "out"], limit: int
    ) -> bool:
        """Reserve once before a side effect; return False for an identical replay."""
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
        now = self._clock()
        quiet = now - self.state.last_activity >= QUIET_RESET_SECONDS
        if not self.state.exchange_id or (quiet and not message.reply_to):
            self.state.exchange_id = uuid4().hex
            self.state.count = 0
        if message.reply_to:
            parent = self.state.messages.get(message.reply_to)
            if (
                parent is None
                or parent.direction == direction
                or parent.exchange_id != self.state.exchange_id
                or parent.state == "failed"
            ):
                raise CallbackError(409, "回复对应的消息不存在或交流已结束")
        if self.state.count >= limit:
            self.state.last_status = "已达连续交流上限"
            self._save()
            raise CallbackError(409, self.state.last_status)
        pending = sum(
            receipt.state in {"queued", "sending", "uncertain"}
            and receipt.exchange_id == self.state.exchange_id
            for receipt in self.state.messages.values()
        )
        if pending >= MAX_PENDING:
            raise CallbackError(429, "待处理消息过多，请稍后再试")
        self.state.messages[message.message_id] = Receipt(
            direction=direction,
            digest=digest,
            exchange_id=self.state.exchange_id,
            reply_to=message.reply_to,
            state="queued" if direction == "in" else "sending",
            text=message.text if direction == "in" else "",
        )
        self.state.count += 1
        self.state.last_activity = now
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
        """A corresponding reply proves an incoming turn has completed."""
        parent = self.state.messages.get(message_id)
        if parent is not None and parent.direction == "in":
            if parent.state == "queued" and self.state.last_status == "等待角色处理":
                self.state.last_status = "角色已处理"
            parent.state, parent.text = "complete", ""
            self._save()

    def pending(self) -> list[BotMessage]:
        """Replay only queued input; host history suppresses already committed turns."""
        return [
            BotMessage(key, receipt.text, receipt.reply_to)
            for key, receipt in self.state.messages.items()
            if receipt.direction == "in" and receipt.state == "queued"
        ]

    def reset(self) -> None:
        """Start a new budget only through an explicit account UI action."""
        if self.pending():
            raise ValueError("仍有待处理消息，不能重置交流")
        self.state.exchange_id = uuid4().hex
        self.state.count = 0
        self.state.last_status = ""
        self.state.last_activity = self._clock()
        self._save()

    @staticmethod
    def purge_saved(kv: KeyValueStore, connection_id: str, peer_id: str) -> None:
        """Deletion must also work when the saved journal cannot be parsed."""
        kv.delete(f"exchange:{connection_id}:{peer_id}")
