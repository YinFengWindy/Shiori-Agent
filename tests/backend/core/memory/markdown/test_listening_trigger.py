"""Storing a listening record checks its group's consolidation in the background."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, cast

import pytest

from conversation.store import ConversationStore
from core.memory.markdown.contracts import ConsolidateResult
from core.memory.markdown.listening_trigger import ListeningTrigger

_GROUP = "thread:mira:qq:g1"


class _Consolidation:
    def __init__(self) -> None:
        self.groups: list[str] = []

    async def consolidate(self, thread_id: str) -> ConsolidateResult:
        self.groups.append(thread_id)
        return ConsolidateResult(trace={"mode": "skipped"})


def _hear(store: ConversationStore, external: str) -> None:
    _ = store.listening.hear(
        _GROUP,
        sender_id="555",
        content="在吗",
        source={},
        external_message_id=external,
        timestamp=datetime(2026, 9, 30, 9, 0).astimezone(),
    )


@pytest.mark.asyncio
async def test_a_stored_record_checks_its_group_until_detached(tmp_path: Path):
    store = ConversationStore(tmp_path / "sessions.db")
    store.listening.switches.set_enabled(_GROUP, True, operator="user")
    consolidation = _Consolidation()
    trigger = ListeningTrigger(cast(Any, consolidation))
    trigger.attach(store.listening)

    _hear(store, "m1")
    await trigger.drain()
    trigger.detach()
    _hear(store, "m2")
    await trigger.drain()

    assert consolidation.groups == [_GROUP]
