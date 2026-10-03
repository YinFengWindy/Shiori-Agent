"""Recent-context projections honor the shared history boundary."""

from pathlib import Path
from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest

from agent.provider import LLMProvider
from conversation.context_scope import UserContextThreads
from conversation.context_scope import load_user_context_threads
from core.identity import IdentityChat, UserIdentityStore
from shiori_sdk.accounts.models import AccountRecord
from conversation.service import desktop_thread_id
from core.memory.markdown.consolidation import _MarkdownConsolidationWorker
from core.memory.markdown.contracts import ConsolidationWindow
from core.memory.markdown.runtime import MarkdownMemoryStore
from core.memory.markdown.recent_context_document import stamp_recent_context
from core.memory.markdown.recent_context_document import visible_recent_context
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
        stamp_recent_context(
            "# 最近发生的事\n\n## 最近聊过的事\nuntil: 2025-01-01\n"
            "- 最近持续关注：既有压缩记忆\n\n## 最近的对话\n[user] previous recent turn\n",
            threads,
        )
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


@pytest.mark.parametrize("operation", ["refresh", "rewrite"])
async def test_rebound_snapshot_does_not_keep_prior_private_compression(
    tmp_path, operation
):
    session, old_threads = _boundary_session()
    worker, memory, provider = _worker(tmp_path)
    provider.chat.return_value.content = '{"active_topics":["old private secret"]}'
    old_snapshot = await worker._build_recent_context_snapshot(
        session=session,
        profile_maint=memory,
        window=ConsolidationWindow(
            old_messages=session.messages,
            keep_count=4,
            consolidate_up_to=len(session.messages),
        ),
        archive_all=False,
        user_threads=old_threads,
    )
    assert isinstance(old_snapshot, str)
    memory.write_recent_context(old_snapshot)
    current = replace(
        old_threads,
        context_since={
            thread: "2026-01-04T00:00:00+00:00" for thread in old_threads.context_since
        },
    )
    provider.chat.reset_mock()
    provider.chat.return_value.content = '{"active_topics":[]}'
    if operation == "refresh":
        await worker.refresh_recent_turns(session=session, user_threads=current)
        assert "old private secret" not in memory.read_recent_context()
    else:
        await worker._build_recent_context_snapshot(
            session=session,
            profile_maint=memory,
            window=ConsolidationWindow(
                old_messages=session.messages,
                keep_count=4,
                consolidate_up_to=len(session.messages),
            ),
            archive_all=False,
            user_threads=current,
        )
        prompt = provider.chat.await_args.kwargs["messages"][-1]["content"]
        assert "old private secret" not in prompt


async def test_binding_change_during_generation_cannot_relabel_old_inputs(tmp_path):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    identities = UserIdentityStore(tmp_path, clock=lambda: now)
    account = AccountRecord(
        id="qq:101",
        plugin_id="qq",
        platform="qq",
        platform_account_id="101",
        config_ref="101",
        role_id="mira",
    )

    def bind():
        return identities.pair(
            identities.create_pairing_code().code,
            record=account,
            user_id="902",
            scope="platform",
            chat=IdentityChat(account.id, "qq", "902"),
        )

    identity = bind()
    assert identity is not None
    original = load_user_context_threads(tmp_path, "mira")
    session = Session("role:mira")
    session.add_message(
        "user",
        "old private secret",
        thread_id=network_thread_id("mira", "qq", "902"),
        timestamp="2026-01-02T00:00:00+00:00",
    )
    worker, memory, provider = _worker(tmp_path)

    async def complete(**kwargs):
        nonlocal now
        identities.unbind(identity.id)
        now = datetime(2026, 1, 4, tzinfo=timezone.utc)
        assert bind()
        return SimpleNamespace(content='{"active_topics":["old private secret"]}')

    provider.chat.side_effect = complete
    snapshot = await worker._build_recent_context_snapshot(
        session=session,
        profile_maint=memory,
        window=ConsolidationWindow(
            old_messages=session.messages, keep_count=0, consolidate_up_to=1
        ),
        archive_all=False,
        user_threads=original,
    )
    assert isinstance(snapshot, str)
    memory.write_recent_context(snapshot)
    assert "old private secret" in visible_recent_context(
        memory.read_recent_context(), original
    )
    assert (
        visible_recent_context(
            memory.read_recent_context(), load_user_context_threads(tmp_path, "mira")
        )
        == ""
    )
