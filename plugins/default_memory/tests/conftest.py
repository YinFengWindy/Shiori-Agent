"""Shared default_memory test fixtures built only on SDK fakes."""

from collections.abc import Callable
from pathlib import Path

import pytest
from shiori_sdk.testing.memory import FakeMemoryStorage

from plugins.default_memory.backend.semantic.store import MemoryStore2


@pytest.fixture
def make_store() -> Callable[..., MemoryStore2]:
    """Opens stores through the storage port, as the host's database lease does."""
    storage = FakeMemoryStorage()

    def make(path: str | Path, **kwargs) -> MemoryStore2:
        return MemoryStore2(path, open_database=storage.open_database, **kwargs)

    return make
