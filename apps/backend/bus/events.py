from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bootstrap.runtime.generations import RuntimeLease
    from agent.policies.delegation import SpawnDecision
    from bus.internal_events import SpawnCompletionEvent


from shiori_sdk.messages import (
    InboundMessage,
)


@dataclass
class SpawnCompletionItem:
    """Typed internal work item，替代 metadata 编解码。"""

    channel: str
    chat_id: str
    event: "SpawnCompletionEvent"
    decision: "SpawnDecision | None" = None
    timestamp: datetime = field(default_factory=datetime.now)
    runtime_lease: RuntimeLease | None = field(default=None, repr=False, compare=False)

    @property
    def session_key(self) -> str:
        return f"{self.channel}:{self.chat_id}"


InboundItem = InboundMessage | SpawnCompletionItem
