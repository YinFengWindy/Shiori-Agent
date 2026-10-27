from __future__ import annotations

import tomllib

import pytest
from desktop_bridge.runtime.apply import RuntimeApplyError
from desktop_bridge.runtime.settings_form import settings_form_write


def test_settings_form_preserves_an_unmigrated_memory_table() -> None:
    derived = settings_form_write(
        {"preserve_plugins": True, "config_toml": "[llm]\nregistrations = []\n"}
    )
    assert derived is not None

    text = derived.build_config_toml(
        '[memory]\nenabled = true\n\n[memory.embedding]\nmodel = "m"\n'
    )

    parsed = tomllib.loads(text)
    assert parsed["memory"]["enabled"] is True
    assert parsed["memory"]["embedding"]["model"] == "m"


def test_settings_form_does_not_invent_a_memory_table() -> None:
    derived = settings_form_write(
        {"preserve_plugins": True, "config_toml": "[llm]\nregistrations = []\n"}
    )
    assert derived is not None

    parsed = tomllib.loads(derived.build_config_toml("[agent]\nmax_tokens = 8\n"))

    assert "memory" not in parsed


def test_settings_form_rejects_memory_in_the_candidate() -> None:
    with pytest.raises(RuntimeApplyError):
        settings_form_write(
            {"preserve_plugins": True, "config_toml": "[memory]\nenabled = true\n"}
        )
