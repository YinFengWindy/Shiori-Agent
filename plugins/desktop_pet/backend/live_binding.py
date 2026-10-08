"""Ends a run once its role stops being the pet's enabled role.

There is no change event to subscribe to: the pet switch is written inside the
host's role-save transaction (``RolePetStateStore.write_draft``) and the SDK
only publishes ``RoleDeleted``. So the run polls. Each check reads the role
manifest's plugin namespace from disk (one small JSON read through
``Roles.extensions.read``) every ``BINDING_CHECK_S``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from .live_clock import Clock

# How often a run re-checks that its role is still the pet's enabled role.
BINDING_CHECK_S = 2.0


async def watch_binding(
    clock: Clock,
    still_bound: Callable[[], bool],
    on_lost: Callable[[], Awaitable[None]],
) -> None:
    """Poll ``still_bound`` and call ``on_lost`` once it turns false."""
    while True:
        await clock.sleep(BINDING_CHECK_S)
        if not still_bound():
            await on_lost()
            return
