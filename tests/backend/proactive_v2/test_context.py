"""AgentTickContext initial state, identity and mutable-field isolation."""

from datetime import timedelta

from proactive_v2.context import AgentTickContext


def test_default_state():
    ctx = AgentTickContext()
    assert ctx.session_key == ""
    assert ctx.context_as_fallback_open is False
    assert ctx.terminal_action is None
    assert ctx.skip_reason == ""
    assert ctx.skip_note == ""
    assert ctx.final_message == ""
    assert ctx.cited_item_ids == []
    assert ctx.steps_taken == 0
    assert ctx.interesting_item_ids == set()
    assert ctx.discarded_item_ids == set()
    assert ctx.fetched_alerts == []
    assert ctx.fetched_contents == []
    assert ctx.fetched_context == []
    assert ctx._alerts_fetched is False
    assert ctx._contents_fetched is False
    assert ctx._context_fetched is False


def test_tick_ids_are_unique_eight_character_identifiers():
    ids = [AgentTickContext().tick_id for _ in range(100)]
    assert len(set(ids)) == 100
    assert all(len(tick_id) == 8 and tick_id.isalnum() for tick_id in ids)


def test_now_utc_is_timezone_aware_utc():
    now = AgentTickContext().now_utc
    assert now.tzinfo is not None
    assert now.utcoffset() == timedelta(0)


def test_interesting_set_is_independent_per_instance():
    ctx1 = AgentTickContext()
    ctx2 = AgentTickContext()
    ctx1.interesting_item_ids.add("feed-mcp:1")
    assert "feed-mcp:1" not in ctx2.interesting_item_ids


def test_discarded_set_is_independent_per_instance():
    ctx1 = AgentTickContext()
    ctx2 = AgentTickContext()
    ctx1.discarded_item_ids.add("feed-mcp:2")
    assert "feed-mcp:2" not in ctx2.discarded_item_ids


def test_cited_item_ids_is_independent_per_instance():
    ctx1 = AgentTickContext()
    ctx2 = AgentTickContext()
    ctx1.cited_item_ids.append("feed-mcp:3")
    assert ctx2.cited_item_ids == []


def test_fetched_alerts_is_independent_per_instance():
    ctx1 = AgentTickContext()
    ctx2 = AgentTickContext()
    ctx1.fetched_alerts.append({"id": "a1"})
    assert ctx2.fetched_alerts == []
