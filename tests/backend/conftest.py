"""Controlled providers with real memory extraction and session commit owners."""

from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest_asyncio

from agent.provider import LLMProvider
from bus.event_bus import EventBus
from shiori_sdk.memory.events import ConsolidationCommitted
from core.memory.group_environment import GroupEnvironment
from core.memory.markdown import (
    MarkdownMemoryMaintenance,
    MarkdownMemoryStore,
    MemoryLifecycleBindRequest,
)
from core.roles import RoleStore
from session.manager import SessionManager


@dataclass
class MemoryHarness:
    manager: SessionManager
    maintenance: MarkdownMemoryMaintenance
    bus: EventBus
    prompts: list[str] = field(default_factory=list)
    events: list[ConsolidationCommitted] = field(default_factory=list)
    fail: bool = False

    def reopen_sessions(self):
        """Rebind runtime callbacks to a fresh session owner using persisted state."""
        manager = SessionManager(self.manager.workspace)
        self.maintenance.bind_lifecycle(
            MemoryLifecycleBindRequest(
                get_session=manager.get_or_create,
                commit_consolidation=manager.commit_consolidation,
                retry_consumers=manager.retry_memory_consumers,
                record_publication=manager.record_memory_publication,
                record_recent_context=manager.record_recent_context,
                after_consolidation=self.maintenance._after_consolidation,
                group_environment=GroupEnvironment(
                    manager.workspace, manager.conversation_store
                ),
                runtime_roles=RoleStore(manager.workspace),
            )
        )
        self.manager = manager
        return manager


@pytest_asyncio.fixture
async def memory_harness(tmp_path: Path):
    """Use deterministic model responses; all production maintenance paths run."""
    manager = SessionManager(tmp_path)
    bus = EventBus()
    harness: MemoryHarness

    async def chat(*, messages: list[dict], **kwargs: Any):
        prompt = str(messages[-1]["content"])
        harness.prompts.append(prompt)
        if harness.fail:
            raise RuntimeError("controlled extraction failure")
        if "近期语境压缩代理" in prompt:
            result = '{"active_topics": ["tea"]}'
        elif prompt.startswith("群环境整理"):
            result = '{"recent_activity": "shared tea", "group_note": "tea"}'
        else:
            result = (
                '{"history_entries": [{"summary": "[2026-10-02 10:00] tea",'
                '"emotional_weight": 3}], "pending_items": '
                '[{"tag": "preference", "content": "likes tea"}]}'
            )
        return SimpleNamespace(content=result)

    maintenance = MarkdownMemoryMaintenance(
        store=MarkdownMemoryStore(tmp_path),
        provider=cast(LLMProvider, SimpleNamespace(chat=chat)),
        model="controlled",
        keep_count=20,
        event_bus=bus,
    )
    maintenance.bind_lifecycle(
        MemoryLifecycleBindRequest(
            get_session=manager.get_or_create,
            commit_consolidation=manager.commit_consolidation,
            retry_consumers=manager.retry_memory_consumers,
            record_publication=manager.record_memory_publication,
            record_recent_context=manager.record_recent_context,
            group_environment=GroupEnvironment(tmp_path, manager.conversation_store),
            runtime_roles=RoleStore(tmp_path),
        )
    )
    harness = MemoryHarness(manager, maintenance, bus)
    bus.on(ConsolidationCommitted, lambda event: harness.events.append(event))
    try:
        yield harness
    finally:
        await maintenance.drain()
        await bus.aclose()
