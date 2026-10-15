"""Only supported Full Access arguments and selected models are emitted."""

import pytest
from pydantic import ValidationError

from plugins.herdr.backend.config import HerdrConfig


def test_full_access_and_model_selection():
    config = HerdrConfig(codex_model="codex-model", claude_model="claude-model")
    assert config.agent_args("codex") == [
        "--dangerously-bypass-approvals-and-sandbox",
        "--model",
        "codex-model",
    ]
    assert config.agent_args("claude") == [
        "--dangerously-skip-permissions",
        "--model",
        "claude-model",
    ]
    with pytest.raises(ValidationError):
        HerdrConfig(session="")


def test_session_defaults_to_herdr_default_and_keeps_a_saved_choice():
    assert HerdrConfig().session == "default"
    assert HerdrConfig.model_validate({"session": "shiori"}).session == "shiori"
