"""FakeCrashReporting follows the host's newest-live-owner hook semantics."""

import asyncio
import logging

from shiori_sdk.testing.crash_reporting import FakeCrashReporting


class _Owner(logging.Handler):
    def system(self, *_args) -> None:
        """Process exception hook."""

    def thread(self, _args) -> None:
        """Thread exception hook."""

    def loop_handler(self, _loop, _context) -> None:
        """Event-loop exception handler."""


def _install(
    reporting: FakeCrashReporting,
    owner: _Owner,
    loop: asyncio.AbstractEventLoop | None = None,
) -> None:
    reporting.install(
        owner, owner, owner.system, owner.thread, loop, owner.loop_handler
    )


def _assert_active(reporting: FakeCrashReporting, owner: _Owner) -> None:
    assert reporting.handler is owner
    assert reporting.system == owner.system
    assert reporting.thread == owner.thread
    assert reporting.loop_handler == owner.loop_handler


def test_retiring_an_older_owner_keeps_the_newest_active():
    reporting, old, new = FakeCrashReporting(), _Owner(), _Owner()
    _install(reporting, old)
    _install(reporting, new)
    reporting.uninstall(old)
    _assert_active(reporting, new)
    assert reporting.owners == [new]


def test_discarding_the_newest_owner_restores_the_previous_generation():
    reporting, active, candidate = FakeCrashReporting(), _Owner(), _Owner()
    _install(reporting, active)
    _install(reporting, candidate)
    reporting.uninstall(candidate)
    _assert_active(reporting, active)
    reporting.uninstall(active)
    assert reporting.owners == []
    assert reporting.handler is None and reporting.system is None


def test_fallback_restores_the_original_loop_handler_across_different_loops():
    first_loop, second_loop = asyncio.new_event_loop(), asyncio.new_event_loop()
    try:
        reporting, active, candidate = FakeCrashReporting(), _Owner(), _Owner()
        _install(reporting, active, first_loop)
        _install(reporting, candidate, second_loop)
        reporting.uninstall(candidate)
        assert reporting.handler is active
        assert reporting.system == active.system
        assert reporting.loop_handler is None
    finally:
        first_loop.close()
        second_loop.close()


def test_owner_installed_twice_is_removed_one_registration_at_a_time():
    reporting, owner = FakeCrashReporting(), _Owner()
    _install(reporting, owner)
    _install(reporting, owner)
    reporting.uninstall(owner)
    _assert_active(reporting, owner)
    assert reporting.owners == [owner]
    reporting.uninstall(owner)
    assert reporting.owners == []
    assert reporting.handler is None and reporting.loop_handler is None
