"""Scene intake starts at publication, or at once in a published generation."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any

from shiori_sdk.core.scene import SCENE, SCENE_HOST, SceneSubject
from shiori_sdk.core.services import BACKGROUND
from shiori_sdk.core.conversation import (
    CONVERSATION,
    ConversationMessage,
    InitiatedMessageCommitted,
)
from shiori_sdk.testing.service_context import FakeServiceContext

from plugins.scene.backend.plugin import setup

PACKAGE_DIR = Path(__file__).resolve().parents[1]

_PROACTIVE = InitiatedMessageCommitted(
    session_key="role:mira",
    channel="desktop",
    role_id="mira",
    thread_id="desktop:mira",
    assistant_response="在吗？",
    source="proactive",
)


class _Conversation:
    """``CONVERSATION.recent_thread_messages``; ``None`` stands for external context."""

    def __init__(self, history: tuple[ConversationMessage, ...] | None) -> None:
        self.history = history
        self.reads = 0

    def recent_thread_messages(
        self, session_key: str, *, thread_id: str, limit: int
    ) -> tuple[ConversationMessage, ...] | None:
        self.reads += 1
        return self.history


class _Host:
    """``SCENE_HOST`` with a publication switch."""

    def __init__(self, *, published: bool) -> None:
        self.published = published
        self._starts: list[Callable[[], None]] = []

    def subject(self, session_key: str, role_id: str) -> SceneSubject | None:
        return SceneSubject(id=role_id, name="Mira", system_prompt="test")

    def legacy_state_paths(self) -> tuple[Path, ...]:
        return ()

    def on_published(self, start: Callable[[], None]) -> Callable[[], None]:
        if self.published:
            start()
            return lambda: None
        self._starts.append(start)
        return lambda: None

    def publish(self) -> None:
        self.published = True
        for start in tuple(self._starts):
            start()
        self._starts.clear()


class _Background:
    """Records observation spawns; the observation itself never runs."""

    def __init__(self) -> None:
        self.names: list[str] = []

    def spawn(self, coro: Coroutine[Any, Any, None], *, name: str) -> asyncio.Task:
        self.names.append(name)
        coro.close()
        return asyncio.create_task(asyncio.sleep(0))


def _context(
    tmp_path: Path, host: _Host, conversation: _Conversation | None = None
) -> FakeServiceContext:
    context = FakeServiceContext("scene", tmp_path, package_dir=PACKAGE_DIR)
    context.serve(SCENE_HOST, host)
    context.serve(
        CONVERSATION,
        conversation or _Conversation((ConversationMessage("user", "hi"),)),
    )
    return context


def _demand(context: FakeServiceContext):
    context.fake_roles.create_role(role_id="mira", name="Mira", system_prompt="test")
    scene = context.kernel.get(SCENE)
    assert scene is not None
    return scene.request(lambda role: role.id == "mira")


async def test_intake_waits_until_the_generation_is_published(tmp_path: Path) -> None:
    host = _Host(published=False)
    context = _context(tmp_path, host)
    background = _Background()
    context.serve(BACKGROUND, background)
    try:
        await setup(context)
        _demand(context)
        await context.fake_events.fanout(_PROACTIVE)
        assert background.names == []

        host.publish()
        await context.fake_events.fanout(_PROACTIVE)

        assert background.names == ["scene_awareness:role:mira"]
    finally:
        await context.aclose()


async def test_setup_in_a_published_generation_listens_at_once(
    tmp_path: Path,
) -> None:
    """An in-generation reload or enable sets the plugin up after publication."""
    host = _Host(published=True)
    context = _context(tmp_path, host)
    background = _Background()
    context.serve(BACKGROUND, background)
    try:
        await setup(context)
        _demand(context)
        await context.fake_events.fanout(_PROACTIVE)

        assert background.names == ["scene_awareness:role:mira"]
    finally:
        await context.aclose()


async def test_only_a_registered_demand_starts_an_observation(tmp_path: Path) -> None:
    """Without a consumer's demand, intake neither reads history nor calls the model."""
    host = _Host(published=True)
    conversation = _Conversation((ConversationMessage("user", "hi"),))
    context = _context(tmp_path, host, conversation)
    background = _Background()
    context.serve(BACKGROUND, background)
    context.fake_roles.create_role(role_id="mira", name="Mira", system_prompt="test")
    try:
        await setup(context)
        scene = context.kernel.get(SCENE)
        assert scene is not None
        await context.fake_events.fanout(_PROACTIVE)
        assert (background.names, conversation.reads) == ([], 0)

        dispose = scene.request(lambda role: role.id == "mira")
        await context.fake_events.fanout(_PROACTIVE)
        assert background.names == ["scene_awareness:role:mira"]

        conversation.history = None  # the thread turned out to be external
        await context.fake_events.fanout(_PROACTIVE)
        assert background.names == ["scene_awareness:role:mira"]

        conversation.history = (ConversationMessage("user", "hi"),)
        dispose()
        await context.fake_events.fanout(_PROACTIVE)
        assert background.names == ["scene_awareness:role:mira"]
    finally:
        await context.aclose()
