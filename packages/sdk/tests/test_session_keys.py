"""Existing role key normalization and stored-key classification."""

import pytest

from shiori_sdk.session_keys import (
    is_role_session_key,
    role_id_from_session_key,
    role_session_key,
)


def test_role_key_normalizes_only_outer_role_whitespace():
    key = role_session_key("  mira:alternate  ")

    assert key == "role:mira:alternate"
    assert role_id_from_session_key(key) == "mira:alternate"


def test_blank_role_cannot_create_a_shared_session_key():
    with pytest.raises(ValueError, match="role_id 不能为空"):
        role_session_key(" \t ")


def test_stored_key_classification_does_not_normalize_the_input():
    assert is_role_session_key("role:mira")
    assert not is_role_session_key(" role:mira")
    # Existing classification requires a suffix, not a valid role id.
    assert is_role_session_key("role: ")
    assert not is_role_session_key("role:")


def test_role_parser_strips_key_and_role_whitespace():
    assert role_id_from_session_key("  role: mira  ") == "mira"
    assert role_id_from_session_key("role: ") == ""


def test_role_parser_does_not_claim_a_transport_session():
    assert not is_role_session_key("telegram:42")
    assert role_id_from_session_key("telegram:42") == ""
