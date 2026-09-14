from dataclasses import replace

import pytest

from agent.config_models import Config
from bootstrap.memory_plugins import load_memory_plugin_module
from bootstrap.runtime.memory import (
    MemoryStorageIncompatibleError,
    validate_memory_transition,
)


def test_existing_vector_storage_allows_connection_changes_but_rejects_new_vector_space(
    tmp_path, monkeypatch
):
    path = tmp_path / "memory.db"
    path.touch()
    monkeypatch.setattr(
        load_memory_plugin_module("default", "config"),
        "resolve_memory_db_path",
        lambda **_: path,
    )
    original = Config(provider="", model="", api_key="", model_registrations=[])
    original.memory.enabled = True
    credentials = replace(
        original,
        memory=replace(
            original.memory,
            embedding=replace(original.memory.embedding, api_key="changed"),
        ),
    )
    validate_memory_transition(original, credentials, tmp_path)
    incompatible = replace(
        original,
        memory=replace(
            original.memory,
            embedding=replace(original.memory.embedding, output_dimensionality=128),
        ),
    )
    with pytest.raises(MemoryStorageIncompatibleError) as failure:
        validate_memory_transition(original, incompatible, tmp_path)
    assert failure.value.to_details()["reason"] == "embedding_migration_required"


def test_new_storage_can_select_its_initial_embedding_space(tmp_path, monkeypatch):
    monkeypatch.setattr(
        load_memory_plugin_module("default", "config"),
        "resolve_memory_db_path",
        lambda **_: tmp_path / "missing.db",
    )
    original = Config(provider="", model="", api_key="", model_registrations=[])
    changed = replace(
        original,
        memory=replace(
            original.memory,
            enabled=True,
            embedding=replace(original.memory.embedding, model="new-embedding"),
        ),
    )
    validate_memory_transition(original, changed, tmp_path)


@pytest.mark.parametrize("selector", ["", " ", " default "])
def test_default_aliases_still_validate_existing_storage(
    tmp_path, monkeypatch, selector
):
    path = tmp_path / "memory.db"
    path.touch()
    monkeypatch.setattr(
        load_memory_plugin_module("default", "config"),
        "resolve_memory_db_path",
        lambda **_: path,
    )
    previous = Config(provider="", model="", api_key="", model_registrations=[])
    candidate = replace(
        previous,
        memory=replace(
            previous.memory,
            enabled=True,
            engine=selector,
            embedding=replace(previous.memory.embedding, model="new-model"),
        ),
    )

    with pytest.raises(MemoryStorageIncompatibleError):
        validate_memory_transition(previous, candidate, tmp_path)


@pytest.mark.parametrize(("enabled", "engine"), [(True, "akasha"), (False, "default")])
def test_non_default_transition_does_not_load_default_package(
    tmp_path, monkeypatch, enabled, engine
):
    def unexpected_load(*_args):
        raise AssertionError("unselected default memory must not load")

    monkeypatch.setattr(
        "bootstrap.runtime.memory.load_memory_plugin_module", unexpected_load
    )
    previous = Config(provider="", model="", api_key="", model_registrations=[])
    candidate = replace(
        previous, memory=replace(previous.memory, enabled=enabled, engine=engine)
    )

    validate_memory_transition(previous, candidate, tmp_path)
