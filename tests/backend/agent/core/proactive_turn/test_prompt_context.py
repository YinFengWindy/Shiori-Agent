import pytest

from agent.core.proactive_turn.prompt_context import build_system_prompt


def test_proactive_system_prompt_rejects_missing_role_identity() -> None:
    with pytest.raises(ValueError, match="role.system_prompt required"):
        build_system_prompt("  ")
