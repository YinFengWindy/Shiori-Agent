"""A published runtime for the real ``PROACTIVE_HOST`` (``HostProactiveRunner``).

Tests hand ``HostProactiveRunner(lambda: runtime)`` a runtime whose leases all
hold one generation. The generation carries only the fields the code under
test reaches (``conversation``, ``tools``, ``config``, ``provider``, ...);
``ProactiveGeneration`` is a plain object so the runner can hold it weakly,
which ``SimpleNamespace`` does not allow.
"""

from __future__ import annotations

from typing import Any

from core.desktop_presence import DesktopPresence


class ProactiveGeneration:
    """One generation's core, made of the given fields."""

    def __init__(self, **fields: Any) -> None:
        self.__dict__.update(fields)


class ProactiveRuntime:
    """A runtime that admits work at once and leases ``core`` every time.

    ``reply_sequences`` is the lease's channel-sequence owner a natural reply
    binds; leave it None when no natural reply opens.
    """

    def __init__(self, core: Any, *, reply_sequences: Any = None) -> None:
        self.core = core
        self.reply_sequences = reply_sequences
        self.desktop_presence = DesktopPresence()

    def acquire(self) -> Any:
        runtime = self

        class _Lease:
            def __init__(self) -> None:
                self.core = runtime.core
                self.reply_sequences = runtime.reply_sequences

            async def __aenter__(self) -> Any:
                return self

            async def __aexit__(self, *_exc: object) -> None:
                return None

        return _Lease()

    async def wait_for_admission(self) -> None:
        return None
