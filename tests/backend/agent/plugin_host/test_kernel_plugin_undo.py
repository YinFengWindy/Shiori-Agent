"""Kernel-loaded ``plugin_undo`` against the host's real session undo protocol.

Reply wording and failure handling are asserted in
``plugins/plugin_undo/tests``; this file only proves the plugin, loaded through
its public package entry, drives the real ``SessionManager`` undo contract and
that kernel unload/reload removes and restores its contributions.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from shiori_sdk.testing.packages import plugin_directory, stage_plugin_package

from agent.lifecycle.phases.before_turn import BeforeTurnFrame
from agent.plugin_host import HostServices, PluginKernel
from bus.event_bus import EventBus
from session.manager import SessionManager


class _MemoryEngine:
    """Records rollback requests and confirms every source id it receives."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def undo_by_message_sources(
        self, message_ids: list[str], *, dry_run: bool = False
    ) -> dict[str, object]:
        self.calls.append({"message_ids": list(message_ids), "dry_run": dry_run})
        return {
            "affected_ids": [],
            "restored_ids": [],
            "rollback_source_ids": list(message_ids),
        }


def _undo_frame(manager: SessionManager, content: str = "/undo") -> BeforeTurnFrame:
    session = manager.get_or_create("cli:1")
    return BeforeTurnFrame(
        input=SimpleNamespace(
            session_key="cli:1",
            session=session,
            context_scope=None,
            msg=SimpleNamespace(
                content=content,
                channel="cli",
                chat_id="1",
                timestamp=datetime.now(),
            ),
        ),
        slots={"session:session": session},
    )


async def _load(tmp_path: Path, manager: SessionManager, memory: _MemoryEngine):
    root = tmp_path / "plugins"
    root.mkdir()
    stage_plugin_package(plugin_directory("plugin_undo"), root / "plugin_undo")
    kernel = PluginKernel(
        [root],
        services=HostServices(
            event_bus=EventBus(), session_manager=manager, memory_engine=memory
        ),
    )
    await kernel.load_all()
    return kernel


async def test_loaded_undo_command_deletes_the_last_turn_from_a_real_session(
    tmp_path: Path,
):
    manager = SessionManager(tmp_path / "workspace")
    session = manager.get_or_create("cli:1")
    session.add_message(
        "user",
        '<system-reminder data-system-context-frame="true">内部</system-reminder>',
    )
    session.add_message("user", "u0")
    session.add_message("assistant", "a0")
    manager.save(session)
    memory = _MemoryEngine()
    kernel = await _load(tmp_path, manager, memory)
    try:
        frame = _undo_frame(manager, " /UNDO@ShioriBot ")
        await kernel.before_turn_modules[0].run(frame)
    finally:
        await kernel.unload("plugin_undo")

    assert frame.slots["session:ctx"].abort is True
    assert manager.get_or_create("cli:1").messages == []
    deleted = ["cli:1:0", "cli:1:1", "cli:1:2"]
    assert memory.calls == [
        {"message_ids": deleted, "dry_run": True},
        {"message_ids": deleted, "dry_run": False},
    ]


async def test_unload_and_reload_remove_and_restore_single_contributions(
    tmp_path: Path,
):
    manager = SessionManager(tmp_path / "workspace")
    memory = _MemoryEngine()
    kernel = await _load(tmp_path, manager, memory)
    try:
        for _ in range(2):
            assert [module.slot for module in kernel.before_turn_modules] == [
                "plugin_undo.undo"
            ]
            assert [name for name, _ in kernel.bot_commands] == ["undo"]
            frame = _undo_frame(manager)
            await kernel.before_turn_modules[0].run(frame)
            assert frame.slots["session:ctx"].abort is True
            assert await kernel.unload("plugin_undo") == []
            assert kernel.before_turn_modules == []
            assert kernel.bot_commands == []
            assert await kernel.load("plugin_undo") is True
    finally:
        await kernel.unload("plugin_undo")
    assert memory.calls == []
