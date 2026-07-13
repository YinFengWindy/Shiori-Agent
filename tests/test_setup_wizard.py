from __future__ import annotations

from bootstrap.setup_wizard import (
    WizardAnswers,
    _render_channels,
    _render_config,
    _render_integrations,
)


def test_render_channels_includes_optional_qqbot_section() -> None:
    rendered = _render_channels(
        WizardAnswers(
            tg_token="telegram-token",
            proactive_enabled=True,
            proactive_channel="telegram",
            proactive_chat_id="123",
        )
    )

    assert "[channels.telegram]" in rendered
    assert "# [plugins.qqbot]" in rendered


def test_render_integrations_omits_removed_fitbit_and_peer_sections() -> None:
    rendered = _render_integrations()

    assert "fitbit" not in rendered
    assert "peer_agents" not in rendered


def test_render_config_omits_removed_proactive_agent_keys() -> None:
    rendered = _render_config(
        WizardAnswers(
            provider="openai",
            model="gpt-main",
            api_key="key",
            base_url="https://example.invalid/v1",
            tg_token="telegram-token",
            proactive_enabled=True,
            proactive_channel="telegram",
            proactive_chat_id="123",
            embed_model="text-embedding-v3",
            embed_api_key="embed-key",
            embed_base_url="https://example.invalid/embed",
        )
    )

    assert "context_prob" not in rendered
    assert "delivery_cooldown_hours" not in rendered
