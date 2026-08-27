from core.common.channel_identifiers import chat_ids_equal, normalize_qq_group_chat_id


def test_qq_group_identifier_accepts_bare_and_prefixed_forms() -> None:
    assert normalize_qq_group_chat_id("831907794") == "gqq:831907794"
    assert chat_ids_equal("qq", "831907794", "gqq:831907794")
    assert not chat_ids_equal("qq", "831907794", "831907795")


def test_non_qq_identifier_does_not_strip_group_prefix() -> None:
    assert not chat_ids_equal("telegram", "831907794", "gqq:831907794")
