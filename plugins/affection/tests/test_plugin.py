"""The affection plugin's RPC surface for its own UI."""

from __future__ import annotations

import pytest

from plugins.affection.backend.plugin import AffectionApi
from plugins.affection.backend.relationship import RoleRelationshipRuntimeService


def test_chat_status_answers_for_a_known_role_and_rejects_others(host) -> None:
    api = AffectionApi(RoleRelationshipRuntimeService(host))

    assert api.chat_status({"role_id": " mira "})["role_id"] == "mira"
    with pytest.raises(ValueError, match="role not found"):
        api.chat_status({"role_id": "ghost"})
