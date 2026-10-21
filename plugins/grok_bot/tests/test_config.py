import pytest
from plugins.grok_bot.backend.config import read_connection


def test_unknown_fields_are_rejected_and_missing_tool_grants_stay_off(config):
    restored = read_connection(config.model_dump())
    assert not (restored.response_rules or {}).get("allow_full_tools", False)
    with pytest.raises(ValueError, match="unexpected"):
        read_connection({**config.model_dump(), "unexpected": "secret"})
