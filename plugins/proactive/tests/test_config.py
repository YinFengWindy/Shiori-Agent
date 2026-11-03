"""ProactiveConfig defaults, removed fields and explicit overrides."""

from plugins.proactive.backend.config import ProactiveConfig


def test_drift_and_runtime_defaults():
    cfg = ProactiveConfig()
    assert cfg.drift_enabled is False
    assert cfg.drift_max_steps == 20
    assert cfg.drift_min_interval_hours == 3
    assert cfg.enabled is False
    assert cfg.delivery_dedupe_hours == 24
    assert cfg.message_dedupe_enabled is True
    assert cfg.message_dedupe_recent_n == 5
