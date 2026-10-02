"""FakeDiagnostics follows the host's newest-live-owner hook semantics."""

import logging

from shiori_sdk.testing.diagnostics import FakeDiagnostics


class _Owner(logging.Handler):
    def system(self, *_args) -> None:
        """Process exception hook."""

    def thread(self, _args) -> None:
        """Thread exception hook."""

    def loop_handler(self, _loop, _context) -> None:
        """Event-loop exception handler."""


def _install(diagnostics: FakeDiagnostics, owner: _Owner) -> None:
    diagnostics.install_global_hooks(
        owner, owner, owner.system, owner.thread, None, owner.loop_handler
    )


def _assert_active(diagnostics: FakeDiagnostics, owner: _Owner) -> None:
    assert diagnostics.handler is owner
    assert diagnostics.system == owner.system
    assert diagnostics.thread == owner.thread
    assert diagnostics.loop_handler == owner.loop_handler


def test_retiring_an_older_owner_keeps_the_newest_active():
    diagnostics, old, new = FakeDiagnostics(), _Owner(), _Owner()
    _install(diagnostics, old)
    _install(diagnostics, new)
    diagnostics.uninstall_global_hooks(old)
    _assert_active(diagnostics, new)
    assert diagnostics.owners == [new]


def test_discarding_the_newest_owner_restores_the_previous_generation():
    diagnostics, active, candidate = FakeDiagnostics(), _Owner(), _Owner()
    _install(diagnostics, active)
    _install(diagnostics, candidate)
    diagnostics.uninstall_global_hooks(candidate)
    _assert_active(diagnostics, active)
    diagnostics.uninstall_global_hooks(active)
    assert diagnostics.owners == []
    assert diagnostics.handler is None and diagnostics.system is None
