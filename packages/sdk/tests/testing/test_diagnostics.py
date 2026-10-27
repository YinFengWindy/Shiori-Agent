"""FakeCrashReporting follows the host's newest-live-owner hook semantics."""

import asyncio
import logging

from shiori_sdk.testing.diagnostics import FakeCrashReporting


class _Owner(logging.Handler):
    def system(self, *_args) -> None:
        """Process exception hook."""

    def thread(self, _args) -> None:
        """Thread exception hook."""

    def loop_handler(self, _loop, _context) -> None:
        """Event-loop exception handler."""


def _install(
    diagnostics: FakeCrashReporting,
    owner: _Owner,
    loop: asyncio.AbstractEventLoop | None = None,
) -> None:
    diagnostics.install(
        owner, owner, owner.system, owner.thread, loop, owner.loop_handler
    )


def _assert_active(diagnostics: FakeCrashReporting, owner: _Owner) -> None:
    assert diagnostics.handler is owner
    assert diagnostics.system == owner.system
    assert diagnostics.thread == owner.thread
    assert diagnostics.loop_handler == owner.loop_handler


def test_retiring_an_older_owner_keeps_the_newest_active():
    diagnostics, old, new = FakeCrashReporting(), _Owner(), _Owner()
    _install(diagnostics, old)
    _install(diagnostics, new)
    diagnostics.uninstall(old)
    _assert_active(diagnostics, new)
    assert diagnostics.owners == [new]


def test_discarding_the_newest_owner_restores_the_previous_generation():
    diagnostics, active, candidate = FakeCrashReporting(), _Owner(), _Owner()
    _install(diagnostics, active)
    _install(diagnostics, candidate)
    diagnostics.uninstall(candidate)
    _assert_active(diagnostics, active)
    diagnostics.uninstall(active)
    assert diagnostics.owners == []
    assert diagnostics.handler is None and diagnostics.system is None


def test_fallback_restores_the_original_loop_handler_across_different_loops():
    first_loop, second_loop = asyncio.new_event_loop(), asyncio.new_event_loop()
    try:
        diagnostics, active, candidate = FakeCrashReporting(), _Owner(), _Owner()
        _install(diagnostics, active, first_loop)
        _install(diagnostics, candidate, second_loop)
        diagnostics.uninstall(candidate)
        assert diagnostics.handler is active
        assert diagnostics.system == active.system
        assert diagnostics.loop_handler is None
    finally:
        first_loop.close()
        second_loop.close()


def test_owner_installed_twice_is_removed_one_registration_at_a_time():
    diagnostics, owner = FakeCrashReporting(), _Owner()
    _install(diagnostics, owner)
    _install(diagnostics, owner)
    diagnostics.uninstall(owner)
    _assert_active(diagnostics, owner)
    assert diagnostics.owners == [owner]
    diagnostics.uninstall(owner)
    assert diagnostics.owners == []
    assert diagnostics.handler is None and diagnostics.loop_handler is None
