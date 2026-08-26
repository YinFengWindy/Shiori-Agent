"""Focused coverage for the proactive configuration input boundary."""

import pytest

from proactive_v2.config_loader import ProactiveConfigError, load_proactive_config


def test_loads_role_execution_settings_from_agent_and_drift_blocks() -> None:
    config = load_proactive_config(
        {
            "enabled": True,
            "profile": "daily",
            "agent": {
                "max_steps": 12,
                "content_limit": 3,
                "web_fetch_max_chars": 4_000,
            },
            "drift": {
                "enabled": True,
                "max_steps": 8,
                "min_interval_hours": 6,
            },
        }
    )

    assert config.agent_tick_max_steps == 12
    assert config.agent_tick_content_limit == 3
    assert config.agent_tick_web_fetch_max_chars == 4_000
    assert config.drift_enabled is True
    assert config.drift_max_steps == 8
    assert config.drift_min_interval_hours == 6


def test_rejects_retired_agent_tick_root_block_via_root_validation() -> None:
    with pytest.raises(ProactiveConfigError, match="非法的根级键: agent_tick"):
        load_proactive_config(
            {
                "profile": "daily",
                "agent_tick": {"max_steps": 12},
            }
        )
