"""Anonymous Telegram senders remain chat subjects; topics are explicit targets."""

from types import SimpleNamespace

from plugins.telegram.backend.channel.identity import (
    message_mentioned_bot,
    message_names,
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


def test_bot_mention_in_text_or_caption_requires_exact_username() -> None:
    assert message_mentioned_bot(
        SimpleNamespace(text="hello @shiori_bot", caption=None), "shiori_bot"
    )
    assert message_mentioned_bot(
        SimpleNamespace(text=None, caption="@SHIORI_BOT photo"), "shiori_bot"
    )
    assert not message_mentioned_bot(
        SimpleNamespace(text="@shiori_bot_extra", caption=None), "shiori_bot"
    )


def test_names_are_the_group_title_and_the_sender_display_name() -> None:
    group = SimpleNamespace(type="supergroup", title="读书会")
    user = SimpleNamespace(full_name="Alice Liu")
    assert message_names(group, user) == {
        "group_name": "读书会",
        "sender_name": "Alice Liu",
    }
    anonymous = SimpleNamespace(full_name=None, title="频道")
    assert message_names(group, anonymous)["sender_name"] == "频道"
    private = SimpleNamespace(type="private", title=None)
    assert message_names(private, user) == {"sender_name": "Alice Liu"}
    assert message_names(private, SimpleNamespace(full_name="")) == {}
