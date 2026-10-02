"""Thread IDs of a role's channel chats share one prefix per role."""

from shiori_sdk.channels.threads import network_thread_id, role_thread_prefix


def test_network_thread_id_is_scoped_by_role_channel_and_chat() -> None:
    thread = network_thread_id("mira", "qq", "gqq:7")

    assert thread == "thread:mira:qq:gqq:7"
    assert thread.startswith(role_thread_prefix("mira"))
    assert not thread.startswith(role_thread_prefix("mi"))
    assert network_thread_id("mira", "qq", "7") != network_thread_id(
        "mira", "qqbot", "7"
    )
