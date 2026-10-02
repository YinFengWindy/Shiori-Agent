"""Collector attribution is delegated to the injected diagnostic owner."""

import logging
import pytest
from types import SimpleNamespace
from shiori_sdk.testing.diagnostics import FakeDiagnostics
from plugins.observe.backend.collector import GlobalErrorCollector


@pytest.mark.asyncio
async def test_injected_context_attribution_flush_and_idempotent_uninstall():
    events = []
    diagnostics = FakeDiagnostics()
    diagnostics.current_session.set("external:1")
    collector = GlobalErrorCollector(SimpleNamespace(emit=events.append), diagnostics)
    collector.install()
    collector.install()
    assert diagnostics.owners == [collector]
    assert diagnostics.handler is not None
    diagnostics.handler.emit(
        logging.LogRecord(
            "external.plugin",
            logging.ERROR,
            "/elsewhere/pkg/plugin.py",
            12,
            "failure 12",
            (),
            None,
        )
    )
    await collector.uninstall()
    await collector.uninstall()
    assert diagnostics.owners == []
    assert len(events) == 1
    assert events[0].session_keys == ["external:1"]
