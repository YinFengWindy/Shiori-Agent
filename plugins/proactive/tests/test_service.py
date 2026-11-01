"""Role loops follow the published binding and the role list; ticks reread settings."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from shiori_sdk.testing.processes import FakeProcesses

from plugins.proactive.backend.loop import ProactiveLoop
from plugins.proactive.backend.service import (
    ProactiveBinding,
    ProactiveService,
    role_proactive_config,
)


class _Host:
    def __init__(self, cap: int) -> None:
        self.cap = cap

    def configured_max_tokens(self) -> int:
        return self.cap

    def web_fetch_available(self) -> bool:
        return False

    def builtin_skills_dir(self) -> str:
        return str(Path("/tmp/shiori-no-builtin-skills"))

    def compile_role_prompt(self, role_id: str) -> str:
        return role_id


class _Role:
    def __init__(self, role_id: str, enabled: bool) -> None:
        self.id = role_id
        self.settings: dict[str, object] = {"enabled": enabled, "profile": "daily"}


class _Settings:
    def __init__(self, role: _Role) -> None:
        self._role = role

    def read(self) -> dict[str, object]:
        return dict(self._role.settings)


class _Roles:
    def __init__(self, *roles: _Role) -> None:
        self.roles = {role.id: role for role in roles}

    def list_roles(self) -> list[_Role]:
        return list(self.roles.values())

    def plugin_settings(self, role_id: str, namespace: str) -> _Settings:
        return _Settings(self.roles[role_id])


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
    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace

    def role_session_key(self, role_id: str) -> str:
        return f"role:{role_id}"


class _Loop:
    """A role loop that runs until stopped; ``unwind`` holds up its exit."""

    instances: list[_Loop] = []

    def __init__(
        self, _sessions: object, config: object, *, max_tokens: int, **_kwargs: object
    ) -> None:
        self.role_id = config.role_id  # type: ignore[attr-defined]
        self.max_tokens = max_tokens
        self.stopped = False
        self.running = False
        self.unwind: asyncio.Event | None = None
        self._stop = asyncio.Event()
        _Loop.instances.append(self)

    def rebind(self, *, max_tokens: int, **_kwargs: object) -> None:
        self.max_tokens = max_tokens

    def stop(self) -> None:
        self.stopped = True
        self._stop.set()

    async def run(self) -> None:
        self.running = True
        try:
            await self._stop.wait()
        finally:
            if self.unwind is not None:
                await self.unwind.wait()
            self.running = False


def _binding(
    workspace: Path,
    roles: _Roles,
    host: _Host,
    *,
    active: bool,
) -> ProactiveBinding:
    return ProactiveBinding(
        host=host,  # type: ignore[arg-type]
        conversation=object(),  # type: ignore[arg-type]
        roles=roles,  # type: ignore[arg-type]
        processes=FakeProcesses(),
        workspace=workspace,
        presence=None,
        markdown=_Markdown(),  # type: ignore[arg-type]
        memory_engine=None,
        scene_followup=False,
        relationship=False,
        affection=None,
        draft_prompt=lambda: None,
        is_active=lambda: active,
    )


def _db(workspace: Path, role_id: str) -> Path:
    return workspace / "roles" / role_id / "proactive.db"


async def _settle() -> None:
    """Lets every ready task run until the role loops are idle again."""
    for _ in range(20):
        await asyncio.sleep(0)


def _running(role_id: str) -> bool:
    return any(
        task.get_name() == f"proactive:{role_id}" for task in asyncio.all_tasks()
    )


async def test_loops_start_at_publication_for_every_role_without_opening_state(
    tmp_path: Path,
) -> None:
    roles = _Roles(_Role("mira", True), _Role("nana", False))
    service = ProactiveService()
    service.attach(_binding(tmp_path, roles, _Host(111), active=True))
    assert not _running("mira")
    try:
        service.published()
        await asyncio.sleep(0)
        assert _running("mira") and _running("nana")
        # The state store opens with a role's first tick, not with its loop.
        assert not _db(tmp_path, "mira").exists()
        assert not _db(tmp_path, "nana").exists()
    finally:
        await service.close()


async def test_a_discarded_candidate_keeps_the_published_max_tokens(
    tmp_path: Path,
) -> None:
    roles = _Roles(_Role("mira", True))
    service = ProactiveService(loop_factory=_Loop)
    service.attach(_binding(tmp_path, roles, _Host(111), active=True))
    try:
        service.published()
        loop = service._loops["mira"].loop
        assert loop.max_tokens == 111
        detach = service.attach(_binding(tmp_path, roles, _Host(999), active=False))
        assert loop.max_tokens == 111
        detach()
        assert loop.max_tokens == 111
    finally:
        await service.close()


async def test_role_create_and_delete_add_and_remove_that_roles_loop(
    tmp_path: Path,
) -> None:
    roles = _Roles()
    service = ProactiveService(loop_factory=_Loop)
    service.attach(_binding(tmp_path, roles, _Host(111), active=True))
    try:
        service.published()
        assert service._loops == {}
        roles.roles["mira"] = _Role("mira", False)
        service.on_roles_changed()
        running = service._loops["mira"]
        del roles.roles["mira"]
        service.on_roles_changed()
        assert "mira" not in service._loops
        assert running.loop.stopped is True
    finally:
        await service.close()


async def test_a_dead_role_loop_is_logged_and_close_raises_it(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    class _Die(_Loop):
        async def run(self) -> None:
            raise RuntimeError(f"{self.role_id} died")

    def factory(_sessions: object, config: object, **kwargs: object) -> object:
        if config.role_id == "mira":  # type: ignore[attr-defined]
            return _Die(_sessions, config, **kwargs)  # type: ignore[arg-type]
        return _Loop(_sessions, config, **kwargs)  # type: ignore[arg-type]

    roles = _Roles(_Role("mira", True), _Role("nana", True))
    service = ProactiveService(loop_factory=factory)
    service.attach(_binding(tmp_path, roles, _Host(111), active=True))
    try:
        with caplog.at_level("ERROR"):
            service.published()
            await asyncio.sleep(0)
        assert service._loops["nana"].task.done() is False
        assert "mira" in caplog.text
        with pytest.raises(RuntimeError, match="mira died"):
            await service.close()
    finally:
        await service.close()


async def test_the_next_reconcile_restarts_a_dead_loop(tmp_path: Path) -> None:
    runs: list[str] = []

    class _DieOnce(_Loop):
        async def run(self) -> None:
            runs.append(self.role_id)
            if len(runs) == 1:
                raise RuntimeError("boom")
            await super().run()

    roles = _Roles(_Role("mira", True))
    service = ProactiveService(loop_factory=_DieOnce)
    service.attach(_binding(tmp_path, roles, _Host(1), active=True))
    service.published()
    await asyncio.sleep(0)
    service.published()  # the next generation
    await asyncio.sleep(0)
    try:
        assert runs == ["mira", "mira"]
        assert not service._loops["mira"].task.done()
    finally:
        with pytest.raises(RuntimeError, match="boom"):
            await service.close()


async def test_a_leaked_cancellation_counts_as_a_dead_loop(tmp_path: Path) -> None:
    class _Leak(_Loop):
        async def run(self) -> None:
            raise asyncio.CancelledError

    roles = _Roles(_Role("mira", True))
    service = ProactiveService(loop_factory=_Leak)
    service.attach(_binding(tmp_path, roles, _Host(1), active=True))
    service.published()
    await asyncio.sleep(0)
    with pytest.raises(RuntimeError, match="意外取消: mira"):
        await service.close()


async def test_a_recreated_role_waits_for_every_earlier_loop_to_finish(
    tmp_path: Path,
) -> None:
    _Loop.instances.clear()
    roles = _Roles(_Role("mira", True))
    service = ProactiveService(loop_factory=_Loop)
    service.attach(_binding(tmp_path, roles, _Host(1), active=True))
    service.published()
    await asyncio.sleep(0)
    first = _Loop.instances[0]
    first.unwind = asyncio.Event()  # e.g. MCP sessions still closing
    for exists in (False, True, False, True):
        if exists:
            roles.roles["mira"] = _Role("mira", True)
        else:
            del roles.roles["mira"]
        service.on_roles_changed()
        await asyncio.sleep(0)
    await _settle()
    try:
        assert first.running
        assert not any(loop.running for loop in _Loop.instances[1:])
        first.unwind.set()
        await _settle()
        assert [loop.running for loop in _Loop.instances] == [False, False, True]
    finally:
        first.unwind.set()
        await service.close()
    assert service._stopping == {}


async def test_close_waits_for_a_loop_that_is_still_unwinding(tmp_path: Path) -> None:
    _Loop.instances.clear()
    roles = _Roles(_Role("mira", True))
    service = ProactiveService(loop_factory=_Loop)
    service.attach(_binding(tmp_path, roles, _Host(1), active=True))
    service.published()
    await asyncio.sleep(0)
    first = _Loop.instances[0]
    first.unwind = asyncio.Event()
    del roles.roles["mira"]
    service.on_roles_changed()
    closing = asyncio.create_task(service.close())
    await _settle()
    assert not closing.done()
    first.unwind.set()
    await closing
    assert not first.running


async def test_each_tick_rereads_the_role_settings(tmp_path: Path) -> None:
    role = _Role("mira", False)
    roles = _Roles(role)
    ticked: list[str] = []

    def read(current: _Roles):
        settings = current.plugin_settings("mira", "proactive").read()
        return role_proactive_config("mira", settings)

    async def dispatch(operation: object) -> None:
        ticked.append(loop.config.profile)

    loop = ProactiveLoop(
        _Sessions(tmp_path),
        read(roles),
        proactive_host=_Host(1),  # type: ignore[arg-type]
        conversation=object(),  # type: ignore[arg-type]
        roles=roles,  # type: ignore[arg-type]
        role_prompt_fn=lambda: "",
        state_path=_db(tmp_path, "mira"),
        processes=FakeProcesses(),
        config_fn=read,  # type: ignore[arg-type]
        tick_dispatcher=dispatch,  # type: ignore[arg-type]
    )
    try:
        await loop._run_tick()
        assert (ticked, _db(tmp_path, "mira").exists()) == ([], False)

        role.settings["enabled"] = True
        await loop._run_tick()
        assert (ticked, _db(tmp_path, "mira").exists()) == (["daily"], True)

        role.settings["profile"] = "quiet"
        await loop._run_tick()
        assert ticked == ["daily", "quiet"]

        role.settings["enabled"] = False
        await loop._run_tick()
        assert ticked == ["daily", "quiet"]
        assert loop._state is None
    finally:
        loop.stop()
        await loop._release()
