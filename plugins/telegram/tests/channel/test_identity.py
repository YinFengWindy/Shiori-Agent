"""Anonymous Telegram senders remain chat subjects; topics are explicit targets."""

from types import SimpleNamespace

from plugins.telegram.backend.channel.identity import (
    message_subject,
    message_topic_metadata,
)


def test_anonymous_sender_chat_precedes_compatibility_user() -> None:
    message = SimpleNamespace(
        sender_chat=SimpleNamespace(id=-1001, username="channel"),
        from_user=SimpleNamespace(id=1087968824, username="GroupAnonymousBot"),
        message_thread_id=42,
    )
    subject, sender_id, kind = message_subject(message)
    assert subject.id == -1001
    assert (sender_id, kind) == ("chat:-1001", "chat")
    assert message_topic_metadata(message) == {"message_thread_id": 42}


def test_regular_user_and_main_chat_have_no_topic() -> None:
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=123, username="alice"),
        message_thread_id=None,
    )
    assert message_subject(message)[1:] == ("123", "user")
    assert message_topic_metadata(message) == {}
