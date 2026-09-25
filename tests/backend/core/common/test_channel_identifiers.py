from core.common.channel_identifiers import (
    bound_qq_group_for_bare_id,
    chat_ids_equal,
    is_bare_qq_group_chat_id,
    normalize_sender_ids,
    normalize_qq_group_chat_id,
)


def test_qq_group_identifier_normalizes_bare_group_number() -> None:
    assert normalize_qq_group_chat_id("831907794") == "gqq:831907794"
    assert normalize_qq_group_chat_id("gqq:831907794") == "gqq:831907794"


def test_bare_qq_id_is_not_the_same_chat_as_the_group() -> None:
    # A bare ID is sent as a private chat; it must never authorize the group.
    assert not chat_ids_equal("qq", "831907794", "gqq:831907794")
    assert chat_ids_equal("qq", " gqq:831907794 ", "gqq:831907794")


def test_non_qq_identifier_does_not_strip_group_prefix() -> None:
    assert not chat_ids_equal("telegram", "831907794", "gqq:831907794")


def test_bare_qq_id_other_than_its_contact_is_a_group() -> None:
    assert is_bare_qq_group_chat_id("831907794", ["3174898512"])
    assert is_bare_qq_group_chat_id("831907794", [])


def test_qq_private_and_prefixed_group_ids_are_not_bare_groups() -> None:
    # Contacts normalize like RoleChannelBindingConfig: strip, drop empty, dedupe.
    assert not is_bare_qq_group_chat_id("123", ["123"])
    assert not is_bare_qq_group_chat_id(" 123 ", [" 123", "123", ""])
    assert not is_bare_qq_group_chat_id("gqq:831907794", ["3174898512"])
    assert not is_bare_qq_group_chat_id("", ["3174898512"])


def test_sender_ids_are_stripped_non_empty_unique_and_sorted() -> None:
    assert normalize_sender_ids([" b", "a", "", "b ", 3]) == ["3", "a", "b"]


def test_bare_qq_id_resolves_to_its_bound_gqq_group() -> None:
    bound = ["gqq:7", "8"]

    assert bound_qq_group_for_bare_id(" 7 ", bound) == "gqq:7"


def test_bare_qq_id_without_bound_group_resolves_to_nothing() -> None:
    # Only a bare ID whose gqq: form is bound counts; prefixed/empty IDs never do.
    assert bound_qq_group_for_bare_id("8", ["gqq:7", "8"]) is None
    assert bound_qq_group_for_bare_id("gqq:7", ["gqq:7"]) is None
    assert bound_qq_group_for_bare_id("", ["gqq:"]) is None
