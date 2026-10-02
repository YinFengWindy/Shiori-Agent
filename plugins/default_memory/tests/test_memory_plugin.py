from dataclasses import replace
from unittest.mock import AsyncMock, Mock

import pytest
from shiori_sdk.memory.build import (
    MemoryBuildConfig,
    MemoryPluginBuildDeps,
    MemoryStorageIncompatibleError,
)
from shiori_sdk.testing.memory import (
    FakeBuildResources,
    FakeMemoryRoles,
    FakeMemoryStorage,
)

from plugins.default_memory.backend.engine import lifecycle
from plugins.default_memory.backend.memory_plugin import MemoryPlugin


def _deps(tmp_path):
    return MemoryPluginBuildDeps(
        config=MemoryBuildConfig(model="model"),
        workspace=tmp_path,
        provider=AsyncMock(),
        light_provider=None,
        requester=AsyncMock(),
        event_publisher=None,
        storage=FakeMemoryStorage(),
        roles=FakeMemoryRoles(("mira",)),
        skills=lambda: ["demo"],
        resources=FakeBuildResources(),
    )


async def test_build_transfers_allocations_and_closes_independently(tmp_path):
    deps = _deps(tmp_path)
    runtime = MemoryPlugin().build(deps)
    assert runtime.engine.describe().name == "default"
    assert len(runtime.resources) == 2
    assert [resource.value for resource in runtime.resources] == runtime.closeables
    await deps.resources.aclose()


async def test_partial_build_registers_database_before_later_constructor_failure(
    tmp_path, monkeypatch
):
    deps = _deps(tmp_path)
    store = Mock()
    monkeypatch.setattr(lifecycle, "MemoryStore2", lambda *args, **kwargs: store)
    monkeypatch.setattr(
        lifecycle, "Embedder", Mock(side_effect=ValueError("bad embedding"))
    )
    with pytest.raises(ValueError, match="bad embedding"):
        MemoryPlugin().build(deps)
    assert len(deps.resources.resources) == 1
    assert deps.resources.transferred is False
    await deps.resources.aclose()
    store.close.assert_called_once()


@pytest.mark.parametrize("change", [{"model": "new"}, {"output_dimensionality": 128}])
def test_vector_change_requires_explicit_migration_and_preserves_data(tmp_path, change):
    deps = _deps(tmp_path)
    path = tmp_path / "plugin-data/default_memory/memory2.db"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"preserved-db")
    candidate = replace(deps.config, embedding=replace(deps.config.embedding, **change))
    with pytest.raises(MemoryStorageIncompatibleError) as failure:
        MemoryPlugin().validate_transition(
            deps.config, candidate, tmp_path, deps.storage
        )
    assert failure.value.to_details()["reason"] == "embedding_migration_required"
    assert path.read_bytes() == b"preserved-db"


def test_credentials_and_absent_storage_do_not_require_vector_migration(tmp_path):
    deps = _deps(tmp_path)
    plugin = MemoryPlugin()
    new_space = replace(
        deps.config, embedding=replace(deps.config.embedding, model="new")
    )
    plugin.validate_transition(deps.config, new_space, tmp_path, deps.storage)
    path = tmp_path / "plugin-data/default_memory/memory2.db"
    path.parent.mkdir(parents=True)
    path.touch()
    credentials = replace(
        deps.config, embedding=replace(deps.config.embedding, api_key="changed")
    )
    plugin.validate_transition(deps.config, credentials, tmp_path, deps.storage)
