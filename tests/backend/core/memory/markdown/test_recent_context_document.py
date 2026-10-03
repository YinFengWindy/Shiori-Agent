"""Derived text keeps the host visibility snapshot that generated it."""

from dataclasses import replace

import pytest

from conversation.context_scope import UserContextThreads
from core.memory.markdown.recent_context_document import (
    stamp_recent_context,
    visible_recent_context,
)


def _threads():
    return UserContextThreads(
        "mira",
        frozenset({"desktop", "private"}),
        {"private": "2026-01-01T00:00:00+00:00"},
    )


def test_additive_binding_keeps_a_prior_snapshot_without_exposing_its_stamp():
    original = _threads()
    content = "# 最近发生的事\n\nprior compression\n"
    stored = stamp_recent_context(content, original)
    added = replace(
        original,
        bound_chat_thread_ids=original.bound_chat_thread_ids | {"new"},
        context_since={**original.context_since, "new": "2026-01-02T00:00:00+00:00"},
    )
    assert visible_recent_context(stored, original) == content
    assert visible_recent_context(stored, added) == content


@pytest.mark.parametrize("change", ["unbind", "rebind", "role", "legacy"])
def test_unknown_or_removed_sources_cannot_be_adopted_under_new_ownership(change):
    original = _threads()
    stored = stamp_recent_context("old private secret", original)
    if change == "unbind":
        current = UserContextThreads("mira", frozenset({"desktop"}))
    elif change == "rebind":
        current = replace(
            original, context_since={"private": "2026-01-04T00:00:00+00:00"}
        )
    elif change == "role":
        current = UserContextThreads("other", frozenset({"other-desktop"}))
    else:
        current, stored = original, "unmarked old private secret"
    assert visible_recent_context(stored, current) == ""
