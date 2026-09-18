import asyncio
import json
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agent.provider import LLMResponse
from memory2.store import MemoryStore2
from bus.event_bus import EventBus
from core.memory.events import ConsolidationCommitted
from plugins.default_memory.backend.engine.lifecycle import DefaultMemoryEngine
from session.manager import ConsolidationCommitRequest, SessionManager


async def test_implicit_long_term_extraction_uses_auxiliary_budget(monkeypatch):
    provider = AsyncMock()
    provider.chat.return_value = LLMResponse(
        content='{"preference":[{"summary":"你喜欢拿铁"}]}'
    )
    engine = DefaultMemoryEngine.__new__(DefaultMemoryEngine)
    monkeypatch.setattr(engine, "_provider", provider, raising=False)
    monkeypatch.setattr(
        engine, "_config", SimpleNamespace(model="memory-model"), raising=False
    )

    result = await engine._extract_implicit_long_term(conversation="USER: 我喜欢拿铁")

    assert result == {"preference": [{"summary": "你喜欢拿铁"}]}
    request = provider.chat.await_args.kwargs
    assert request["call_purpose"] == "auxiliary"
    assert request["max_tokens"] == 600


@pytest.mark.asyncio
async def test_post_response_extraction_receives_current_role_memory(tmp_path) -> None:
    store = MemoryStore2(tmp_path / "memory2.db")
    try:
        store.upsert_item(
            "preference",
            "你喜欢拿铁",
            embedding=None,
            extra={"role_id": "mira"},
        )
        store.upsert_item(
            "preference",
            "你喜欢红茶",
            embedding=None,
            extra={"role_id": "atlas"},
        )
        engine = object.__new__(DefaultMemoryEngine)
        engine._v2_store = store
        engine._extract_implicit_long_term = AsyncMock(return_value=None)

        await engine._extract_and_save_post_response(
            user_msg="我还喜欢摩卡",
            assistant_response="记住了",
            source_ref="role:mira@post_response",
            channel="desktop",
            chat_id="role:mira",
            role_id="mira",
        )

        existing_profile = engine._extract_implicit_long_term.await_args.kwargs[
            "existing_profile"
        ]
        assert "你喜欢拿铁" in existing_profile
        assert "你喜欢红茶" not in existing_profile
    finally:
        store.close()


class _ConcurrentMemorizer:
    def __init__(self, store: MemoryStore2):
        self.store = store
        self.started = asyncio.Event()
        self.failed = asyncio.Event()
        self.release = threading.Event()
        self.finished = asyncio.Event()
        self.error = RuntimeError("first memory save failed")
        self.item_ids: list[str] = []
        self.loop = asyncio.get_running_loop()

    async def save_from_consolidation(
        self, history_entry: str, source_ref: str, **_kwargs: object
    ) -> None:
        if history_entry == "failure":
            await self.started.wait()
            self.failed.set()
            raise self.error
        await asyncio.to_thread(self._delayed_save, source_ref)

    def _delayed_save(self, source_ref: str) -> None:
        self.loop.call_soon_threadsafe(self.started.set)
        if not self.release.wait(timeout=5):
            raise TimeoutError("test did not release delayed memory write")
        result = self.store.upsert_item(
            memory_type="event",
            summary="delayed memory",
            embedding=[0.1, 0.2],
            source_ref=source_ref,
        )
        self.item_ids.append(result.split(":", 1)[1])
        self.loop.call_soon_threadsafe(self.finished.set)


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel_count", [0, 1, 2])
async def test_failed_parallel_consumer_settles_writes_before_undo_and_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cancel_count: int
):
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("role:mira")
    for index in range(3):
        session.add_message("user", f"question {index}")
        session.add_message("assistant", f"answer {index}")
    manager.save(session)
    message_ids = tuple(message["id"] for message in session.messages)
    store = MemoryStore2(tmp_path / "memory2.db")
    memorizer = _ConcurrentMemorizer(store)
    engine = DefaultMemoryEngine.__new__(DefaultMemoryEngine)
    engine._v2_store = store
    monkeypatch.setattr(engine, "_memorizer", memorizer, raising=False)
    implicit = AsyncMock(return_value=None)
    monkeypatch.setattr(engine, "_extract_implicit_long_term", implicit)
    bus = EventBus()
    bus.on(ConsolidationCommitted, engine._on_consolidation_committed)
    event = ConsolidationCommitted(
        history_entry_payloads=[("failure", 0), ("delayed", 0)],
        source_ref=json.dumps(message_ids),
        scope_channel="desktop",
        scope_chat_id=session.key,
        conversation="question 2",
        role_id="mira",
    )

    async def publish():
        await bus.emit(event)

    def resolve_sources(message_ids: list[str]) -> list[str]:
        preview = engine.undo_by_message_sources(message_ids, dry_run=True)
        sources = preview["rollback_source_ids"]
        assert isinstance(sources, list)
        return [str(source) for source in sources]

    async def undo_session():
        result = await manager.undo_last_turn(
            session.key, rollback_source_resolver=resolve_sources
        )
        assert result is not None
        return engine.undo_by_message_sources(result.deleted_ids)

    task = asyncio.create_task(
        manager.commit_consolidation(
            ConsolidationCommitRequest(session.key, message_ids, 0, 6),
            AsyncMock(),
            publish,
        )
    )
    undo_task = None
    try:
        await asyncio.wait_for(memorizer.failed.wait(), timeout=2)
        for _ in range(cancel_count):
            task.cancel()
            await asyncio.sleep(0)
        undo_task = asyncio.create_task(undo_session())
        # Let the failing child, gather completion and queued undo all take their turns.
        for _ in range(5):
            await asyncio.sleep(0)
        assert not undo_task.done()
        assert not task.done()
        assert session.last_consolidated == 6
        assert len(session.messages) == 6
        memorizer.release.set()
        outcome, cleanup = await asyncio.wait_for(
            asyncio.gather(task, undo_task, return_exceptions=True), timeout=2
        )
        if cancel_count:
            assert isinstance(outcome, asyncio.CancelledError)
        else:
            assert outcome is memorizer.error
        assert isinstance(cleanup, dict)
        assert cleanup["affected_ids"] == memorizer.item_ids
        assert memorizer.finished.is_set()
        assert store.get_items_by_ids(memorizer.item_ids)[0]["status"] == "superseded"
        assert len(session.messages) == 4
        assert session.last_consolidated == 0
        implicit.assert_not_awaited()
        manager.invalidate(session.key)
        assert manager.get_or_create(session.key).last_consolidated == 0
    finally:
        memorizer.release.set()
        await asyncio.gather(
            task, *([undo_task] if undo_task else []), return_exceptions=True
        )
        await asyncio.wait_for(memorizer.finished.wait(), timeout=2)
        store.close()
        await bus.aclose()
