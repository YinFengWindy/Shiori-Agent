"""Quiesces accepted runtime work before replacing process-global channel identity."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bootstrap.channel_host import ChannelHost
    from bootstrap.runtime.background import RuntimeBackground
    from bootstrap.runtime.generations import RuntimeCandidate


@asynccontextmanager
async def channel_handover_barrier(
    host: ChannelHost,
    candidate: RuntimeCandidate,
    *,
    current: RuntimeCandidate,
    accepted: tuple[RuntimeCandidate, ...],
    background_groups: Mapping[RuntimeCandidate, RuntimeBackground],
    admission: asyncio.Event,
    drain_outbound: Callable[[], Awaitable[None]],
    restore_background: Callable[[], None],
):
    """Drains published versions while leaving prepared candidate work untouched."""
    candidate_host = candidate.channel_host
    if candidate_host is None:
        raise RuntimeError("Channel handover requires a prepared channel host")
    if not host.requires_exclusive_handover(candidate_host):
        yield accepted
        return

    groups = [
        background_groups[generation]
        for generation in accepted
        if generation in background_groups
    ]
    current_group = background_groups.get(current)
    stopped_current = False
    failure: BaseException | None = None
    admission.clear()
    try:
        # Intake can fail after partially pausing channels, so it belongs inside
        # the same recovery boundary as background drain and durable commit.
        host.pause_intake()
        # stop() cancels in-flight background work, so a model call stuck in
        # retries cannot hold admission closed; replies it already queued are
        # still delivered by drain_outbound below.
        for group in groups:
            if group is current_group:
                stopped_current = True
            group.stop()
        results = await asyncio.gather(
            *(group.drain() for group in groups), return_exceptions=True
        )
        errors = [result for result in results if isinstance(result, BaseException)]
        if errors:
            raise BaseExceptionGroup("Accepted background work failed to drain", errors)
        await asyncio.gather(*(generation.wait_for_work() for generation in accepted))
        await drain_outbound()
        yield accepted
    except BaseException as error:
        failure = error
        raise
    finally:
        recovery_errors: list[BaseException] = []
        try:
            if stopped_current and not candidate.published:
                try:
                    restore_background()
                except BaseException as error:
                    recovery_errors.append(error)
            if not candidate.published:
                try:
                    host.resume_intake()
                except BaseException as error:
                    recovery_errors.append(error)
        finally:
            admission.set()
        if recovery_errors:
            if failure is not None:
                recovery_errors.insert(0, failure)
            raise BaseExceptionGroup(
                "Channel handover recovery failed", recovery_errors
            )
