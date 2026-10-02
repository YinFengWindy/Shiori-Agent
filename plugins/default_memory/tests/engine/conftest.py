"""Shared construction fixture for testing individual default-engine mixins."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from shiori_sdk.testing.memory import FakeMemoryRoles

from plugins.default_memory.backend.engine import DefaultMemoryEngine


def _make_default_engine(
    *,
    config=None,
    provider=None,
    retriever=None,
    memorizer=None,
    tagger=None,
    post_response_worker=None,
    event_publisher=None,
    v2_store=None,
):
    engine = DefaultMemoryEngine.__new__(DefaultMemoryEngine)
    engine._config = config or SimpleNamespace(model="lm")
    engine._workspace = Path(".")
    engine._roles = FakeMemoryRoles()
    engine._provider = provider
    engine._light_provider = None
    engine._light_model = ""
    engine._v2_store = v2_store
    engine._embedder = None
    engine._memorizer = memorizer
    engine._retriever = retriever
    engine._tagger = tagger
    engine._post_response_worker = post_response_worker
    engine._event_bus = event_publisher
    engine._wire_memory2_events()
    return engine


@pytest.fixture
def make_engine():
    """Provides a factory with explicit fake inputs and no host bootstrap."""
    return _make_default_engine
