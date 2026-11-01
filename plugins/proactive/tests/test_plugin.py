"""Publication starts role loops and the scene subscription; setup does not."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from pydantic import ValidationError

from shiori_sdk.core.affection import AFFECTION
from shiori_sdk.core.conversation import CONVERSATION
from shiori_sdk.core.markdown_memory import MARKDOWN_MEMORY
from shiori_sdk.core.models import MAIN_MODEL
from shiori_sdk.core.proactive_host import PROACTIVE_HOST
from shiori_sdk.core.services import ROLES
from shiori_sdk.core.sessions import SESSIONS
from shiori_sdk.role_events import RoleCreated, SceneObservationCommitted
from shiori_sdk.testing.events import FakeEvents
from shiori_sdk.testing.service_context import FakeServiceContext

from plugins.proactive.backend.plugin import setup
from plugins.proactive.backend.turn.scene_subscription import SceneFollowupSubscription

PACKAGE_DIR = Path(__file__).resolve().parents[1]


class _Host:
    def web_fetch_available(self) -> bool:
        return False

    def configured_max_tokens(self) -> int:
        return 128

    def builtin_skills_dir(self) -> str:
        return str(Path("/tmp/shiori-no-builtin-skills"))

    def compile_role_prompt(self, role_id: str) -> str:
        return role_id


class _Role:
    def __init__(self, role_id: str, enabled: bool) -> None:
        self.id = role_id
        self.settings = {"enabled": enabled, "profile": "daily"}


class _Settings:
    def __init__(self, role: _Role) -> None:
        self._role = role

    def read(self) -> dict[str, object]:
        return dict(self._role.settings)


class _Roles:
    def __init__(self, *roles: _Role) -> None:
        self._roles = {role.id: role for role in roles}

    def add(self, role: _Role) -> None:
        self._roles[role.id] = role

    def list_roles(self) -> list[_Role]:
        return list(self._roles.values())

    def plugin_settings(self, role_id: str, namespace: str) -> _Settings:
        return _Settings(self._roles[role_id])


class _Docs:
    def read_long_term(self) -> str:
        return ""

    def read_self(self) -> str:
        return ""

    def read_recent_context(self) -> str:
        return ""


class _Markdown:
    def role(self, role_id: str) -> _Docs:
        return _Docs()


class _Sessions:
    @property
    def presence(self) -> None:
        return None


class _Affection:
    def __init__(self) -> None:
        self.calls = 0

    def apply_scene_decision(
        self, session_key: str, transition: str, scene_key: str
    ) -> None:
        self.calls += 1


def _context(
    tmp_path: Path, *, model: str | None, scene_followup: bool = True
) -> FakeServiceContext:
    context = FakeServiceContext(
        "proactive",
        tmp_path,
        package_dir=PACKAGE_DIR,
        config=(
            {} if scene_followup else {"scene_followup": False, "relationship": False}
        ),
    )
    context.fake_process_resources.active = False
    if model is not None:
        context.serve(MAIN_MODEL, model)
    context.serve(PROACTIVE_HOST, _Host())  # type: ignore[arg-type]
    context.serve(CONVERSATION, object())  # type: ignore[arg-type]
    context.serve(MARKDOWN_MEMORY, _Markdown())  # type: ignore[arg-type]
    context.serve(SESSIONS, _Sessions())  # type: ignore[arg-type]
    return context


def _scene_event() -> SceneObservationCommitted:
    return SceneObservationCommitted(
        session_key="role:mira",
        channel="desktop",
        chat_id="role:mira",
        role_id="mira",
        source="passive",
        transition="started",
        scene_key="rain",
    )


def _loop_running(role_id: str) -> bool:
    return any(
        task.get_name() == f"proactive:{role_id}" for task in asyncio.all_tasks()
    )


async def test_role_loops_start_at_publication_and_follow_new_roles(
    tmp_path: Path,
) -> None:
    roles = _Roles(_Role("mira", False))
    context = _context(tmp_path, model="m")
    context.serve(ROLES, roles)  # type: ignore[arg-type]
    try:
        await setup(context)
        await context.fake_events.fanout(RoleCreated("mira"))
        assert not _loop_running("mira")

        context.fake_process_resources.publish()
        await asyncio.sleep(0)
        assert _loop_running("mira")
        roles.add(_Role("nana", True))
        await context.fake_events.fanout(RoleCreated("nana"))
        await asyncio.sleep(0)
        assert _loop_running("nana")
        # Loops open nothing until a tick runs.
        assert not (tmp_path / "roles").exists()
    finally:
        await context.aclose()


async def test_scene_followup_applies_only_after_publication(tmp_path: Path) -> None:
    affection = _Affection()
    context = _context(tmp_path, model=None)
    context.serve(AFFECTION, affection)  # type: ignore[arg-type]
    context.serve(ROLES, _Roles(_Role("mira", True)))  # type: ignore[arg-type]
    event = _scene_event()
    try:
        await setup(context)
        await context.fake_events.fanout(event)
        assert affection.calls == 0
        assert not (tmp_path / "roles" / "mira" / "proactive.db").exists()
        context.fake_process_resources.publish()
        await context.fake_events.fanout(event)
        assert affection.calls == 1
        assert not (tmp_path / "roles" / "mira" / "proactive.db").exists()
    finally:
        await context.aclose()


async def test_scene_followup_switch_off_does_not_apply(tmp_path: Path) -> None:
    affection = _Affection()
    context = _context(tmp_path, model="m", scene_followup=False)
    context.serve(AFFECTION, affection)  # type: ignore[arg-type]
    context.serve(ROLES, _Roles(_Role("mira", False)))  # type: ignore[arg-type]
    try:
        await setup(context)
        context.fake_process_resources.publish()
        await context.fake_events.fanout(_scene_event())
        assert affection.calls == 0
    finally:
        await context.aclose()


async def test_each_generations_scene_subscription_applies_until_stopped() -> None:
    bus_a, bus_b = FakeEvents(), FakeEvents()
    first, second = _Affection(), _Affection()
    older = SceneFollowupSubscription(bus_a, lambda: first)
    newer = SceneFollowupSubscription(bus_b, lambda: second)
    older.start()
    newer.start()
    event = _scene_event()
    await bus_a.fanout(event)
    await bus_b.fanout(event)
    assert (first.calls, second.calls) == (1, 1)
    older.stop()
    await bus_a.fanout(event)
    await bus_b.fanout(event)
    assert (first.calls, second.calls) == (1, 2)


async def test_a_non_boolean_switch_fails_setup(tmp_path: Path) -> None:
    context = FakeServiceContext(
        "proactive",
        tmp_path,
        package_dir=PACKAGE_DIR,
        config={"scene_followup": "false"},
    )
    context.serve(ROLES, _Roles())  # type: ignore[arg-type]
    try:
        with pytest.raises(ValidationError, match="scene_followup"):
            await setup(context)
    finally:
        await context.aclose()
