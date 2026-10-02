from dataclasses import replace

import pytest
from agent.config_models import Config
from bootstrap.runtime.memory import validate_memory_transition
from shiori_sdk.memory.build import MemoryStorageIncompatibleError


def test_existing_vector_storage_allows_connection_changes_but_rejects_new_vector_space(
    tmp_path, monkeypatch
):
    path = tmp_path / "memory.db"
    path.touch()
    config_path = tmp_path / "plugin-data/default_memory/config.local.toml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text('db_path = "memory.db"', encoding="utf-8")
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
    config_path = tmp_path / "plugin-data/default_memory/config.local.toml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text('db_path = "memory.db"', encoding="utf-8")
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


def test_disabled_transition_does_not_load_default_package(tmp_path, monkeypatch):
    def unexpected_load(*_args):
        raise AssertionError("unselected default memory must not load")

    monkeypatch.setattr("bootstrap.wiring.resolve_memory_plugin", unexpected_load)
    previous = Config(provider="", model="", api_key="", model_registrations=[])
    candidate = replace(
        previous, memory=replace(previous.memory, enabled=False, engine="default")
    )

    validate_memory_transition(previous, candidate, tmp_path)


@pytest.mark.parametrize("location", ["legacy", "migrated"])
@pytest.mark.parametrize(
    "change", [{"model": "different-embedding"}, {"output_dimensionality": 128}]
)
def test_custom_database_blocks_incompatible_vectors_before_and_after_config_migration(
    tmp_path, location, change
):

    workspace = tmp_path / "workspace"
    db_path = workspace / "custom/vectors.db"
    db_path.parent.mkdir(parents=True)
    db_path.touch()
    config_path = (
        workspace
        / ("plugins" if location == "legacy" else "plugin-data")
        / "default_memory/config.local.toml"
    )
    config_path.parent.mkdir(parents=True)
    config_path.write_text('db_path = "custom/vectors.db"\n', encoding="utf-8")
    previous = Config(provider="", model="", api_key="", model_registrations=[])
    previous.memory.enabled = True
    candidate = replace(
        previous,
        memory=replace(
            previous.memory, embedding=replace(previous.memory.embedding, **change)
        ),
    )
    assert not (workspace / "memory/memory2.db").exists()
    with pytest.raises(MemoryStorageIncompatibleError):
        validate_memory_transition(previous, candidate, workspace)
    target = workspace / "plugin-data/default_memory/config.local.toml"
    assert target.is_file()
    with pytest.raises(MemoryStorageIncompatibleError):
        validate_memory_transition(previous, candidate, workspace)
