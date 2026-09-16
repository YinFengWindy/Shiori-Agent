"""ProactiveConfig defaults, removed fields and explicit overrides."""

from proactive_v2.config import ProactiveConfig


def test_loop_and_web_defaults():
    cfg = ProactiveConfig()
    assert cfg.agent_tick_max_steps == 35
    assert isinstance(cfg.agent_tick_max_steps, int)
    assert cfg.agent_tick_content_limit == 5
    assert isinstance(cfg.agent_tick_content_limit, int)
    assert cfg.agent_tick_web_fetch_max_chars == 8_000
    assert isinstance(cfg.agent_tick_web_fetch_max_chars, int)


def test_drift_and_runtime_defaults():
    cfg = ProactiveConfig()
    assert cfg.drift_enabled is False
    assert cfg.drift_max_steps == 20
    assert cfg.drift_min_interval_hours == 3
    assert cfg.enabled is False
    assert cfg.delivery_dedupe_hours == 24
    assert cfg.message_dedupe_enabled is True
    assert cfg.message_dedupe_recent_n == 5


def test_obsolete_fields_are_absent():
    cfg = ProactiveConfig()
    for name in (
        "use_agent_tick",
        "agent_tick_model",
        "agent_tick_context_prob",
        "agent_tick_delivery_cooldown_hours",
        "drift_dir",
        "context_only_daily_max",
        "context_only_min_interval_hours",
    ):
        assert not hasattr(cfg, name), name


def test_explicit_loop_and_web_overrides():
    cfg = ProactiveConfig(agent_tick_max_steps=10, agent_tick_web_fetch_max_chars=4_000)
    assert cfg.agent_tick_max_steps == 10
    assert cfg.agent_tick_web_fetch_max_chars == 4_000
