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


def _error(message: str) -> logging.LogRecord:
    return logging.LogRecord(
        "external.plugin", logging.ERROR, "/elsewhere/plugin.py", 1, message, (), None
    )


@pytest.mark.asyncio
async def test_retiring_the_old_collector_keeps_the_new_one_recording_once():
    diagnostics = FakeDiagnostics()
    old_events, new_events = [], []
    old = GlobalErrorCollector(SimpleNamespace(emit=old_events.append), diagnostics)
    new = GlobalErrorCollector(SimpleNamespace(emit=new_events.append), diagnostics)
    old.install()
    new.install()
    try:
        await old.uninstall()
        assert diagnostics.owners == [new]
        assert diagnostics.system == new._on_sys_except
        assert diagnostics.handler is not None
        diagnostics.handler.emit(_error("one observed error"))
        await new.uninstall()
        assert old_events == []
        assert len(new_events) == 1 and new_events[0].count == 1
    finally:
        await new.uninstall()
        await old.uninstall()


@pytest.mark.asyncio
async def test_discarded_candidate_collector_restores_the_active_generation():
    diagnostics = FakeDiagnostics()
    events, discarded = [], []
    active = GlobalErrorCollector(SimpleNamespace(emit=events.append), diagnostics)
    candidate = GlobalErrorCollector(
        SimpleNamespace(emit=discarded.append), diagnostics
    )
    active.install()
    candidate.install()
    try:
        await candidate.uninstall()
        assert diagnostics.owners == [active]
        assert diagnostics.system == active._on_sys_except
        assert diagnostics.handler is not None
        diagnostics.handler.emit(_error("active remains"))
        await active.uninstall()
        assert len(events) == 1
        assert discarded == []
    finally:
        await candidate.uninstall()
        await active.uninstall()
