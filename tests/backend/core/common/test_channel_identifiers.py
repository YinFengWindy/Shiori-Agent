from core.common.channel_identifiers import normalize_sender_id


def test_sender_ids_drop_surrounding_space_and_a_leading_at_marker() -> None:
    assert normalize_sender_id(" @alice ") == "alice"
    assert normalize_sender_id(" @ bob") == "bob"
    assert normalize_sender_id("a@b") == "a@b"
