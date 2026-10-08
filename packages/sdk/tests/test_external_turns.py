import pytest

from shiori_sdk.external_turns import ExternalTurnMessage

FIELDS = {
    "role_id": "mira",
    "platform": " bilibili ",
    "conversation_id": "room-1",
    "conversation_title": "直播间",
    "sender_id": "uid-7",
    "sender_name": "观众七",
    "message_id": "m1",
    "text": " 主播好 ",
}


def test_identifiers_are_stripped_but_text_is_kept():
    message = ExternalTurnMessage(**FIELDS)

    assert (message.platform, message.text) == ("bilibili", " 主播好 ")


@pytest.mark.parametrize("field", sorted(FIELDS))
def test_every_field_is_required(field):
    with pytest.raises(ValueError, match=field):
        ExternalTurnMessage(**{**FIELDS, field: "  "})
