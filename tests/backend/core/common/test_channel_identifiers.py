from core.common.channel_identifiers import chat_ids_equal, normalize_qq_group_chat_id


def test_qq_group_identifier_normalizes_bare_group_number() -> None:
    assert normalize_qq_group_chat_id("831907794") == "gqq:831907794"
    assert normalize_qq_group_chat_id("gqq:831907794") == "gqq:831907794"


def test_bare_qq_id_is_not_the_same_chat_as_the_group() -> None:
    # A bare ID is sent as a private chat; it must never authorize the group.
    assert not chat_ids_equal("qq", "831907794", "gqq:831907794")
    assert chat_ids_equal("qq", " gqq:831907794 ", "gqq:831907794")


def test_non_qq_identifier_does_not_strip_group_prefix() -> None:
    assert not chat_ids_equal("telegram", "831907794", "gqq:831907794")
