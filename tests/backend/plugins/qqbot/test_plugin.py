from __future__ import annotations

from types import SimpleNamespace
from typing import cast

from plugins.qqbot.plugin import QQBotConfigModel, QQBotPlugin


def test_qqbot_plugin_skips_channel_without_credentials() -> None:
    plugin = QQBotPlugin()
    plugin.context = cast(object, SimpleNamespace(config=QQBotConfigModel()))

    assert plugin.channels() == []


def test_qqbot_plugin_accepts_legacy_config_aliases() -> None:
    plugin = QQBotPlugin()
    plugin.context = cast(
        object,
        SimpleNamespace(
            config=QQBotConfigModel.model_validate(
                {
                    "appId": "app",
                    "clientSecret": "secret",
                    "allow_from": ["user-openid"],
                }
            )
        ),
    )

    channels = plugin.channels()

    assert len(channels) == 1
    assert channels[0].name == "qqbot"
    assert channels[0]._app_id == "app"
    assert channels[0]._client_secret == "secret"
    assert channels[0]._allow_from == {"user-openid"}
