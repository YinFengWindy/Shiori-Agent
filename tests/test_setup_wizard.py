from __future__ import annotations

from bootstrap.setup_wizard import (
    WizardAnswers,
    _render_channels,
    _render_integrations,
)


def test_render_channels_omits_removed_qqbot_section() -> None:
    rendered = _render_channels(
        WizardAnswers(
            tg_token="telegram-token",
            tg_allow_from=["alice"],
            proactive_enabled=True,
            proactive_channel="telegram",
            proactive_chat_id="123",
        )
    )

    assert "[channels.telegram]" in rendered
    assert "[plugins.qqbot]" not in rendered


def test_render_integrations_omits_removed_fitbit_and_peer_sections() -> None:
    rendered = _render_integrations()

    assert "fitbit" not in rendered
    assert "peer_agents" not in rendered
