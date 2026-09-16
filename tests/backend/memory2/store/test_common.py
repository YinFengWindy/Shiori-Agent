"""Hotness contracts exercise the scoring function used by vector retrieval."""

from datetime import datetime, timedelta, timezone

import pytest

from memory2.store.common import _hotness_score


def test_hotness_rewards_fresh_access_and_decays_at_configured_half_life():
    now = datetime(2026, 9, 16, tzinfo=timezone.utc)
    assert _hotness_score(20, now, now=now) > 0.9
    assert _hotness_score(1, now - timedelta(days=90), now=now) < 0.05
    # A non-default half-life detects implementations that ignore the parameter.
    fresh = _hotness_score(5, now, now=now, half_life_days=7)
    aged = _hotness_score(5, now - timedelta(days=7), now=now, half_life_days=7)
    assert aged == pytest.approx(fresh / 2)
