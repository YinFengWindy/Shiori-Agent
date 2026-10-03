"""Recent-context projections honor the shared history boundary."""

from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest

from agent.provider import LLMProvider
from conversation.context_scope import UserContextThreads
from conversation.service import desktop_thread_id
from core.memory.markdown.consolidation import _MarkdownConsolidationWorker
from core.memory.markdown.contracts import ConsolidationWindow
from core.memory.markdown.runtime import MarkdownMemoryStore
from session.manager import Session
from shiori_sdk.channels.threads import network_thread_id


def _boundary_session():
    desktop = desktop_thread_id("mira")
    bound = network_thread_id("mira", "qq", "902")
    threads = UserContextThreads(
        "mira",
        frozenset({desktop, bound}),
        context_since={bound: "2026-01-01T00:00:10+00:00"},
    )
    session = Session("role:mira")
    for thread, content, timestamp in (
        (bound, "excluded compact DM", "2026-01-01T00:00:09+00:00"),
        (desktop, "existing desktop", "2026-01-01T00:00:00+00:00"),
        (bound, "binding boundary DM", "2026-01-01T00:00:10+00:00"),
        (bound, "new DM", "2026-01-01T00:00:11+00:00"),
        (bound, "excluded tail DM", "2026-01-01T00:00:08+00:00"),
    ):
        session.add_message("user", content, thread_id=thread, timestamp=timestamp)
    return session, threads


def _worker(tmp_path: Path):
    memory = MarkdownMemoryStore(tmp_path / "roles" / "mira")
    provider = SimpleNamespace(
        chat=AsyncMock(return_value=SimpleNamespace(content='{"active_topics":[]}'))
    )
    worker = _MarkdownConsolidationWorker(
        profile_maint=memory,
        provider=cast(LLMProvider, provider),
        model="test",
        keep_count=4,
    )
    return worker, memory, provider


@pytest.mark.asyncio
@pytest.mark.parametrize("archive_all", [False, True])
async def test_recent_context_filters_compact_source_and_tail_before_rendering(
    tmp_path: Path,
    archive_all: bool,
):
    session, threads = _boundary_session()
    worker, memory, provider = _worker(tmp_path)
    window = ConsolidationWindow(
        old_messages=session.messages[:2],
        keep_count=4,
        consolidate_up_to=2,
    )

    snapshot = await worker._build_recent_context_snapshot(
        session=session,
        profile_maint=memory,
        window=window,
        archive_all=archive_all,
        user_threads=threads,
    )

    assert isinstance(snapshot, str)
    prompt = provider.chat.await_args.kwargs["messages"][-1]["content"]
    assert "excluded compact DM" not in prompt
    assert "excluded tail DM" not in prompt
    assert "existing desktop" in prompt
    assert "[user] binding boundary DM" in snapshot
    assert "[user] new DM" in snapshot
    assert "excluded" not in snapshot
    assert len(session.messages) == 5


@pytest.mark.asyncio
async def test_recent_turn_refresh_excludes_old_dm_and_keeps_prior_compression(
    tmp_path: Path,
):
    session, threads = _boundary_session()
    worker, memory, provider = _worker(tmp_path)
    memory.write_recent_context(
        "# 最近发生的事\n\n## 最近聊过的事\nuntil: 2025-01-01\n"
        "- 最近持续关注：既有压缩记忆\n\n## 最近的对话\n[user] previous recent turn\n"
    )

    await worker.refresh_recent_turns(session=session, user_threads=threads)

    snapshot = memory.read_recent_context()
    assert "既有压缩记忆" in snapshot
    assert "until: 2025-01-01" in snapshot
    assert "[user] binding boundary DM" in snapshot
    assert "[user] new DM" in snapshot
    assert "excluded" not in snapshot
    assert "previous recent turn" not in snapshot
    provider.chat.assert_not_awaited()
