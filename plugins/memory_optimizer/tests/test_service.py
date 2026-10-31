"""The loop: published bindings only, their interval, and surviving a failed round."""

from __future__ import annotations

import asyncio

from plugins.memory_optimizer.backend.service import (
    MemoryOptimizerService,
    OptimizerBinding,
)

from .conftest import FakeMarkdownMemory


class CountingRoles:
    """No roles; counts the rounds that listed them, the first ``failures`` raise."""

    def __init__(self, failures: int = 0) -> None:
        self.calls = 0
        self.failures = failures

    def list_roles(self) -> list[object]:
        self.calls += 1
        if self.calls <= self.failures:
            raise OSError("roles unreadable")
        return []


def _binding(
    roles: CountingRoles, *, interval_seconds: int = 1, active: bool = True
) -> OptimizerBinding:
    # One-second boundaries: every round is about a second after the last.
    return OptimizerBinding(
        roles=roles,  # type: ignore[arg-type]
        memory=FakeMarkdownMemory(),
        models=object(),  # type: ignore[arg-type]
        interval_seconds=interval_seconds,
        is_active=lambda: active,
    )


async def _until(condition, timeout: float = 5.0) -> None:
    async def poll() -> None:
        while not condition():
            await asyncio.sleep(0.02)

    await asyncio.wait_for(poll(), timeout=timeout)


async def test_a_failed_round_is_skipped_and_the_next_round_runs() -> None:
    service = MemoryOptimizerService()
    roles = CountingRoles(failures=1)
    _ = service.attach(_binding(roles))
    try:
        await _until(lambda: roles.calls >= 2)
    finally:
        await service.close()


async def test_a_discarded_candidate_leaves_the_published_interval() -> None:
    service = MemoryOptimizerService()
    published = CountingRoles()
    _ = service.attach(_binding(published))
    try:
        await _until(lambda: published.calls >= 1)
        candidate = service.attach(
            _binding(CountingRoles(), interval_seconds=3600, active=False)
        )
        candidate()
        # Still every second, not every hour.
        await _until(lambda: published.calls >= 3)
    finally:
        await service.close()


async def test_nothing_runs_before_a_binding_is_published() -> None:
    service = MemoryOptimizerService()
    roles = CountingRoles()
    _ = service.attach(_binding(roles, active=False))
    try:
        await asyncio.sleep(0.3)
        assert roles.calls == 0
    finally:
        await service.close()
