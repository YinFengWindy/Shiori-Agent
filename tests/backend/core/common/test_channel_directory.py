from __future__ import annotations

from core.common.channel_directory import ChannelDirectory


class _PlainChannel:
    name = "plain"


class _HookedChannel:
    name = "hooked"
    default_chat_type = "private"

    def supports_stream_events(self, chat_id: str) -> bool:
        return chat_id == "live"

    def system_prompt_hint(self, chat_id: str) -> str:
        return f"\n## Rules for {chat_id}\n"


def _directory(*channels: object) -> ChannelDirectory:
    by_name = {getattr(channel, "name"): channel for channel in channels}
    directory = ChannelDirectory()
    directory.bind(by_name.get)
    return directory


def test_unbound_directory_only_streams_role_owned_desktop_sessions() -> None:
    directory = ChannelDirectory()

    assert directory.supports_stream_events("desktop", "role:mira")
    assert not directory.supports_stream_events("desktop", "role:")
    assert not directory.supports_stream_events("desktop", "desktop:direct")
    assert not directory.supports_stream_events("telegram", "123")
    assert directory.system_prompt_hint("telegram", "123") == ""
    assert directory.default_chat_type("telegram") == "unknown"


def test_channels_without_hooks_get_neutral_defaults() -> None:
    directory = _directory(_PlainChannel())

    assert not directory.supports_stream_events("plain", "live")
    assert directory.system_prompt_hint("plain", "live") == ""
    assert directory.default_chat_type("plain") == "unknown"


def test_channel_hooks_answer_for_their_own_name_only() -> None:
    directory = _directory(_PlainChannel(), _HookedChannel())

    assert directory.supports_stream_events("hooked", "live")
    assert not directory.supports_stream_events("hooked", "other")
    assert directory.system_prompt_hint("hooked", "c1") == "## Rules for c1"
    assert directory.default_chat_type("hooked") == "private"
    assert not directory.supports_stream_events("missing", "live")


def test_rebinding_switches_to_the_new_channel_set() -> None:
    directory = _directory(_HookedChannel())
    directory.bind({"plain": _PlainChannel()}.get)

    assert not directory.supports_stream_events("hooked", "live")
