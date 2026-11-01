"""Role loops follow the published binding and report a loop that dies."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from plugins.proactive.backend.service import ProactiveBinding, ProactiveService


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
        return self._role.settings


class _Roles:
    def __init__(self, *roles: _Role) -> None:
        self._roles = {role.id: role for role in roles}

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


class _Loop:
    def __init__(
        self, _sessions: object, config: object, *, max_tokens: int, **_kwargs: object
    ) -> None:
        self.role_id = config.role_id  # type: ignore[attr-defined]
        self.max_tokens = max_tokens
        self.stopped = False
        self._stop = asyncio.Event()

    def rebind(self, *, max_tokens: int, **_kwargs: object) -> None:
        self.max_tokens = max_tokens

    def stop(self) -> None:
        self.stopped = True
        self._stop.set()

    async def run(self) -> None:
        await self._stop.wait()


class _Die:
    def stop(self) -> None:
        return None

    def rebind(self, **_kwargs: object) -> None:
        return None

    async def run(self) -> None:
        raise RuntimeError("mira died")


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


async def test_attach_does_not_open_the_state_db_until_published(
    tmp_path: Path,
) -> None:
    roles = _Roles(_Role("mira", True))
    service = ProactiveService()
    service.attach(_binding(tmp_path, roles, _Host(111), active=True))
    assert not _db(tmp_path, "mira").exists()
    assert not any(task.get_name() == "proactive:mira" for task in asyncio.all_tasks())
    try:
        service.published()
        assert _db(tmp_path, "mira").is_file()
        assert any(task.get_name() == "proactive:mira" for task in asyncio.all_tasks())
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


async def test_role_switch_adds_and_removes_that_roles_loop(tmp_path: Path) -> None:
    mira = _Role("mira", False)
    service = ProactiveService(loop_factory=_Loop)
    service.attach(_binding(tmp_path, _Roles(mira), _Host(111), active=True))
    try:
        service.published()
        assert "mira" not in service._loops
        mira.settings["enabled"] = True
        service.on_roles_changed()
        running = service._loops["mira"]
        mira.settings["enabled"] = False
        service.on_roles_changed()
        assert "mira" not in service._loops
        assert running.loop.stopped is True
    finally:
        await service.close()


async def test_a_dead_role_loop_is_logged_and_close_raises_it(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    def factory(_sessions: object, config: object, **_kwargs: object) -> object:
        if config.role_id == "mira":  # type: ignore[attr-defined]
            return _Die()
        return _Loop(_sessions, config, max_tokens=1)

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
