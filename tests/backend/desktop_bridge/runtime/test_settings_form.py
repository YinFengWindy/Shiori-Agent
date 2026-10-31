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


def test_settings_form_merges_scene_observation_without_dropping_plugin_keys() -> None:
    derived = settings_form_write(
        {
            "preserve_plugins": True,
            "config_toml": "[agent]\nmax_tokens = 8\n",
            "scene_observation_enabled": False,
        }
    )
    assert derived is not None
    assert derived.fingerprint_payload["scene_observation_enabled"] is False

    text = derived.build_config_toml(
        '[plugins.scene]\nenabled = true\nlabel = "keep"\n\n[plugins.other]\nenabled = false\n'
    )

    parsed = tomllib.loads(text)
    assert parsed["agent"]["max_tokens"] == 8
    assert parsed["plugins"]["scene"] == {
        "enabled": True,
        "label": "keep",
        "observation_enabled": False,
    }
    assert parsed["plugins"]["other"]["enabled"] is False
    assert "scene_observation" not in parsed.get("agent", {})


def test_settings_form_absent_scene_flag_does_not_invent_the_plugin_key() -> None:
    derived = settings_form_write(
        {"preserve_plugins": True, "config_toml": "[agent]\nmax_tokens = 8\n"}
    )
    assert derived is not None
    assert "scene_observation_enabled" not in derived.fingerprint_payload

    parsed = tomllib.loads(
        derived.build_config_toml("[plugins.scene]\nenabled = true\n")
    )

    assert parsed["plugins"]["scene"] == {"enabled": True}


def test_settings_form_scene_flag_creates_the_plugin_table() -> None:
    derived = settings_form_write(
        {
            "preserve_plugins": True,
            "config_toml": "[llm]\nregistrations = []\n",
            "scene_observation_enabled": False,
        }
    )
    assert derived is not None

    parsed = tomllib.loads(derived.build_config_toml("[agent]\nmax_tokens = 8\n"))

    assert parsed["plugins"]["scene"]["observation_enabled"] is False


def test_settings_form_merges_proactive_switches_without_dropping_plugin_keys() -> None:
    derived = settings_form_write(
        {
            "preserve_plugins": True,
            "config_toml": "[agent]\nmax_tokens = 8\n",
            "proactive_strategies": {"scene_followup": False},
        }
    )
    assert derived is not None
    assert derived.fingerprint_payload["proactive_strategies"] == {
        "scene_followup": False
    }

    text = derived.build_config_toml(
        '[plugins.proactive]\nenabled = true\nlabel = "keep"\n'
        "relationship = true\n\n[plugins.other]\nenabled = false\n"
    )

    parsed = tomllib.loads(text)
    assert parsed["plugins"]["proactive"] == {
        "enabled": True,
        "label": "keep",
        "relationship": True,
        "scene_followup": False,
    }
    assert parsed["plugins"]["other"]["enabled"] is False
    assert "proactive_strategies" not in parsed.get("agent", {})


def test_settings_form_absent_proactive_payload_does_not_invent_the_table() -> None:
    derived = settings_form_write(
        {"preserve_plugins": True, "config_toml": "[agent]\nmax_tokens = 8\n"}
    )
    assert derived is not None
    assert "proactive_strategies" not in derived.fingerprint_payload

    parsed = tomllib.loads(derived.build_config_toml("[agent]\nmax_tokens = 8\n"))

    assert "plugins" not in parsed


def test_settings_form_rejects_a_non_boolean_proactive_switch() -> None:
    with pytest.raises(RuntimeApplyError, match="必须是布尔值"):
        settings_form_write(
            {
                "preserve_plugins": True,
                "config_toml": "[llm]\nregistrations = []\n",
                "proactive_strategies": {"relationship": "false"},
            }
        )


def test_settings_form_rejects_a_non_boolean_scene_flag() -> None:
    with pytest.raises(RuntimeApplyError):
        settings_form_write(
            {
                "preserve_plugins": True,
                "config_toml": "[llm]\nregistrations = []\n",
                "scene_observation_enabled": "false",
            }
        )
