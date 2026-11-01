"""A published runtime for the real ``PROACTIVE_HOST`` (``HostProactiveRunner``).

Tests hand ``HostProactiveRunner(lambda: runtime)`` a runtime whose leases all
hold one generation. The generation carries only the fields the code under
test reaches (``conversation``, ``tools``, ``config``, ``provider``, ...);
``ProactiveGeneration`` is a plain object so the runner can hold it weakly,
which ``SimpleNamespace`` does not allow. ``plugin_role_loops`` builds the
proactive plugin's loops on such a port.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from core.desktop_presence import DesktopPresence
from core.memory.markdown.host import HostMarkdownMemory
from core.roles import RoleStore
from core.roles.plugin_capability import HostRoles
from plugins.proactive.backend.loop import ProactiveLoop
from plugins.proactive.backend.plugin import (
    _RESOURCE_KEY,  # pyright: ignore[reportPrivateUsage]
    setup,
)
from plugins.proactive.backend.service import ProactiveService
from session.manager import SessionManager
from shiori_sdk.core.affection import AFFECTION
from shiori_sdk.core.conversation import CONVERSATION
from shiori_sdk.core.markdown_memory import MARKDOWN_MEMORY
from shiori_sdk.core.models import MAIN_MODEL
from shiori_sdk.core.proactive_host import PROACTIVE_HOST
from shiori_sdk.core.reply_policy import REPLY_POLICY
from shiori_sdk.core.services import ROLES
from shiori_sdk.core.sessions import SESSIONS
from shiori_sdk.testing.service_context import FakeServiceContext

PROACTIVE_PLUGIN_DIR = Path(__file__).resolve().parents[2] / "plugins" / "proactive"


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


@asynccontextmanager
async def plugin_role_loops(
    workspace: Path,
    *,
    roles: RoleStore,
    sessions: SessionManager,
    proactive_host: Any,
    conversation: Any,
    affection: Any = None,
    policy: Any = None,
    scene_followup: bool = False,
    relationship: bool = True,
) -> AsyncIterator[dict[str, Any]]:
    """Every role's loop as the proactive plugin builds it, ticked by hand.

    The plugin's own ``setup`` and ``ProactiveService`` build the loops on a
    published generation with the given host services; the loops never
    schedule a tick (``_run_loop`` waits for stop), the test drives them.
    """
    context = FakeServiceContext(
        "proactive",
        workspace,
        package_dir=PROACTIVE_PLUGIN_DIR,
        config={"scene_followup": scene_followup, "relationship": relationship},
    )
    context.serve(ROLES, HostRoles(roles))
    context.serve(SESSIONS, sessions)
    context.serve(MARKDOWN_MEMORY, HostMarkdownMemory(workspace, roles))
    context.serve(PROACTIVE_HOST, proactive_host)
    context.serve(CONVERSATION, conversation)
    context.serve(MAIN_MODEL, "m")
    if affection is not None:
        context.serve(AFFECTION, affection)
    if policy is not None:
        context.serve(REPLY_POLICY, policy)
    service = context.fake_process_resources.acquire(
        _RESOURCE_KEY, lambda: ProactiveService(loop_factory=_HandTickedLoop)
    )
    try:
        await setup(context)
        yield {
            role_id: running.loop
            for role_id, running in service._loops.items()  # pyright: ignore[reportPrivateUsage]
        }
    finally:
        await context.aclose()


class _HandTickedLoop(ProactiveLoop):
    """The production loop that schedules no tick of its own."""

    async def _run_loop(self) -> None:
        await self._stop_requested.wait()  # pyright: ignore[reportPrivateUsage]
