from __future__ import annotations

import pytest
from agent.config_models import Config
from bootstrap.memory_capabilities import default_memory_enabled, memory_build_config


def _config(**plugins: dict) -> Config:
    return Config(
        provider="",
        model="chat",
        api_key="primary",
        light_api_key="light",
        light_base_url="https://light.example",
        base_url="https://primary.example",
        plugins=plugins,
        model_registrations=[],
    )


def test_memory_build_config_does_not_fall_back_to_chat_credentials() -> None:
    built = memory_build_config(_config())

    assert built.embedding.api_key == ""
    assert built.embedding.base_url == ""
    assert built.embedding.model == "text-embedding-v3"
    assert built.model == "chat"
    assert built.light_model == "chat"


def test_memory_build_config_reads_the_plugin_table() -> None:
    built = memory_build_config(
        _config(
            default_memory={
                "enabled": True,
                "embedding_model": "embed",
                "embedding_api_key": "plugin-key",
                "embedding_base_url": "https://embed.example",
                "output_dimensionality": 1024,
            }
        )
    )

    assert built.embedding.model == "embed"
    assert built.embedding.api_key == "plugin-key"
    assert built.embedding.base_url == "https://embed.example"
    assert built.embedding.output_dimensionality == 1024


def test_memory_build_config_keeps_an_explicit_empty_model() -> None:
    built = memory_build_config(_config(default_memory={"embedding_model": ""}))

    assert built.embedding.model == ""


def test_memory_build_config_rejects_non_positive_dimensionality() -> None:
    with pytest.raises(ValueError, match="output_dimensionality"):
        memory_build_config(_config(default_memory={"output_dimensionality": 0}))


def test_default_memory_enabled_uses_the_manifest_default_or_explicit_flag() -> None:
    assert default_memory_enabled(_config()) is True
    assert default_memory_enabled(_config(default_memory={"enabled": False})) is False
    assert default_memory_enabled(_config(default_memory={"enabled": True})) is True
