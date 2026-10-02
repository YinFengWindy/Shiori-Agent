from __future__ import annotations

from pathlib import Path


from shiori_sdk.testing.channel_context import FakeChannelDeclarations

PLUGIN_DIR = Path(__file__).resolve().parents[1]


def test_manifest_declares_the_telegram_channel_without_host_config() -> None:
    manifest = FakeChannelDeclarations(PLUGIN_DIR)
    assert manifest is not None
    assert manifest.values["id"] == "telegram"
    # Bots and their Tokens live in plugin storage, not in [plugins.telegram].
    assert set(manifest.values["capabilities"]) == {
        "channels",
        "accounts",
        "avatars",
        "kv",
        "config",
        "rpc",
    }
    assert manifest.values.get("config_model") is None
    assert [item["name"] for item in manifest.values["channels"]] == ["telegram"]
    assert manifest.values["channels"][0]["label"] == "Telegram"
    # Labels the member IDs of a group rule's blacklist.
    assert manifest.values["channels"][0]["contact_label"]
    # Telegram group IDs are negative numbers without a prefix.
    types = {item.type: item.prefix for item in manifest.channel_chat_types("telegram")}
    assert types == {"private": None, "group": None}


def test_channels_are_generation_owned() -> None:
    from plugins.telegram.backend.channel import TelegramChannel

    assert TelegramChannel(token="123:abc").configuration_key is None


def test_channel_registers_bot_commands() -> None:
    from plugins.telegram.backend.channel import TelegramChannel

    assert TelegramChannel.uses_bot_commands is True
