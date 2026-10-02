import asyncio
import logging
import sys
from types import SimpleNamespace

import pytest

from plugins.observe.backend.collector import GlobalErrorCollector
from core.common.diagnostics import HostDiagnostics


@pytest.mark.asyncio
async def test_old_collector_retirement_preserves_new_hooks_and_records_once():
    previous = sys.excepthook
    old_events, new_events = [], []
    old = GlobalErrorCollector(
        SimpleNamespace(emit=old_events.append), HostDiagnostics()
    )
    new = GlobalErrorCollector(
        SimpleNamespace(emit=new_events.append), HostDiagnostics()
    )
    old.install()
    new.install()
    try:
        logging.getLogger("app.test").error("one observed error")
        await old.uninstall()
        assert sys.excepthook == new._on_sys_except
        assert asyncio.get_running_loop().get_exception_handler() == new._on_loop_except
        await new.uninstall()
        assert not old_events
        assert len(new_events) == 1
        assert new_events[0].count == 1
        assert sys.excepthook == previous
    finally:
        await new.uninstall()
        await old.uninstall()


@pytest.mark.asyncio
async def test_discarded_collector_restores_active_generation():
    events = []
    active = GlobalErrorCollector(
        SimpleNamespace(emit=events.append), HostDiagnostics()
    )
    candidate = GlobalErrorCollector(
        SimpleNamespace(emit=lambda event: None), HostDiagnostics()
    )
    active.install()
    candidate.install()
    try:
        await candidate.uninstall()
        assert sys.excepthook == active._on_sys_except
        logging.getLogger("app.test").error("active remains")
        await active.uninstall()
        assert len(events) == 1
    finally:
        await candidate.uninstall()
        await active.uninstall()
