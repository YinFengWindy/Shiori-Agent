"""Stored records and the periodic sweep check groups' consolidation in the background."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path
from typing import Any, cast

import pytest

from conversation.store import ConversationStore
from core.memory.markdown.contracts import ConsolidateResult
from core.memory.markdown.listening_trigger import ListeningTrigger

_GROUP = "thread:mira:qq:g1"
_STRANDED = "thread:mira:qq:g2"


class _Consolidation:
    def __init__(self, pending: list[str] | None = None) -> None:
        self.groups: list[str] = []
        self.pending = pending or []

    def pending_groups(self) -> list[str]:
        return list(self.pending)

    async def consolidate(self, thread_id: str, *, today: date) -> ConsolidateResult:
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


async def _until(done: Callable[[], bool]) -> None:
    for _ in range(100):
        if done():
            return
        await asyncio.sleep(0)
    raise AssertionError("condition not reached")


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


@pytest.mark.asyncio
async def test_starting_sweeps_groups_left_with_records_and_detach_ends_it():
    # 没有新消息的群，积压的记录在启动时的检查里就被整理，不等下一条消息。
    consolidation = _Consolidation(pending=[_STRANDED])
    trigger = ListeningTrigger(cast(Any, consolidation), sweep_interval_s=3600)

    trigger.start()
    await _until(lambda: consolidation.groups == [_STRANDED])
    trigger.detach()
    await asyncio.wait_for(trigger.drain(), timeout=1)

    assert consolidation.groups == [_STRANDED]
