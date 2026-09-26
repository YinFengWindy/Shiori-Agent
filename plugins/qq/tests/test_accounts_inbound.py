from __future__ import annotations

from plugins.qq.backend.accounts_inbound import inbound_message


def test_group_event_preserves_account_group_and_member_identity():
    message = inbound_message(
        account_id="account-a",
        expected_uin="101",
        event={
            "post_type": "message",
            "message_type": "group",
            "self_id": 101,
            "group_id": 777,
            "user_id": 902,
            "message_id": 45,
            "raw_message": "[CQ:at,qq=101] hello",
        },
    )
    assert message is not None
    assert (message.channel, message.chat_id, message.sender) == (
        "qq",
        "gqq:777",
        "902",
    )
    assert message.metadata == {
        "account_id": "account-a",
        "platform_account_id": "101",
        "chat_type": "group",
        "sender_id": "902",
        "external_message_id": "45",
        "group_id": "777",
        "mentioned": True,
    }


def test_group_trigger_uses_the_actual_account_qq_number():
    base = {
        "post_type": "message",
        "message_type": "group",
        "self_id": 202,
        "group_id": 777,
        "user_id": 902,
        "raw_message": "hello",
    }
    unmentioned = inbound_message(account_id="b", expected_uin="202", event=base)
    assert unmentioned is not None
    assert unmentioned.metadata["mentioned"] is False
    wrong_at = {**base, "raw_message": "[CQ:at,qq=101] hello"}
    other_mention = inbound_message(account_id="b", expected_uin="202", event=wrong_at)
    assert other_mention is not None
    assert other_mention.metadata["mentioned"] is False
    addressed = {**base, "raw_message": "[CQ:at,qq=202] hello"}
    own_mention = inbound_message(account_id="b", expected_uin="202", event=addressed)
    assert own_mention is not None
    assert own_mention.metadata["mentioned"] is True


def test_other_account_event_is_rejected():
    assert (
        inbound_message(
            account_id="account-a",
            expected_uin="101",
            event={
                "post_type": "message",
                "message_type": "private",
                "self_id": 202,
                "user_id": 902,
                "raw_message": "wrong account",
            },
        )
        is None
    )
