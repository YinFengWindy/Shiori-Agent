from __future__ import annotations

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent.plugin_host import HostServices, PluginKernel
from bus.event_bus import EventBus
from plugins.plugin_undo.backend.plugin import PluginUndo, UndoCommandModule
from session.manager import SessionManager
from shiori_plugin_testkit.packages import stage_plugin_package


class _MemoryEngine:
    def __init__(self, *, fail_real_undo: bool = False) -> None:
        self.calls: list[dict[str, object]] = []
        self.fail_real_undo = fail_real_undo

    def undo_by_message_sources(
        self,
        message_ids: list[str],
        *,
        dry_run: bool = False,
    ) -> dict[str, object]:
        self.calls.append({"message_ids": list(message_ids), "dry_run": dry_run})
        if self.fail_real_undo and not dry_run:
            raise RuntimeError("memory cleanup failed")
        return {
            "affected_ids": ["mem1"],
            "restored_ids": ["old1"],
            "rollback_source_ids": ["cli:1:0", "cli:1:1", "cli:1:2"],
        }


@pytest.mark.asyncio
async def test_undo_command_aborts_without_running_llm(tmp_path):
    session_manager = SessionManager(tmp_path)
    session = session_manager.get_or_create("cli:1")
    session.add_message(
        "user",
        '<system-reminder data-system-context-frame="true">内部</system-reminder>',
    )
    session.add_message("user", "u0")
    session.add_message("assistant", "a0")
    session_manager.save(session)
    memory_engine = _MemoryEngine()
    plugin = PluginUndo(session_manager, memory_engine)
    module = UndoCommandModule(plugin)
    state = SimpleNamespace(
        session_key="cli:1",
        session=session,
        msg=SimpleNamespace(
            content=" /UNDO@ShioriBot ",
            channel="cli",
            chat_id="1",
            timestamp=datetime.now(),
        ),
    )
    frame = SimpleNamespace(input=state, slots={"session:session": state.session})

    result = await module.run(frame)

    ctx = result.slots["session:ctx"]
    assert ctx.abort is True
    assert "已撤销上一轮对话" in ctx.abort_reply
    assert [call["dry_run"] for call in memory_engine.calls] == [True, False]
    assert session_manager.get_or_create("cli:1").messages == []


@pytest.mark.asyncio
async def test_undo_reports_memory_cleanup_failure_after_session_delete(
    tmp_path, caplog
):
    session_manager = SessionManager(tmp_path)
    session = session_manager.get_or_create("cli:1")
    session.add_message("user", "u0")
    session.add_message("assistant", "a0")
    session_manager.save(session)
    memory_engine = _MemoryEngine(fail_real_undo=True)
    plugin = PluginUndo(session_manager, memory_engine)

    with caplog.at_level("ERROR", logger="plugin.undo"):
        reply = await plugin.undo("cli:1")

    assert "已撤销上一轮对话，但记忆清理失败" in reply
    assert session_manager.get_or_create("cli:1").messages == []
    assert [call["dry_run"] for call in memory_engine.calls] == [True, False]
    assert "deleted_ids=['cli:1:0', 'cli:1:1']" in caplog.text
    assert "'affected_ids': ['mem1']" in caplog.text


@pytest.mark.asyncio
async def test_undo_reports_no_passive_turn_without_touching_memory(tmp_path):
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("cli:1")
    session.add_message("assistant", "proactive", proactive=True)
    manager.save(session)
    memory = _MemoryEngine()

    reply = await PluginUndo(manager, memory).undo(session.key)

    assert reply == "没有可撤销的上一轮对话。"
    assert memory.calls == []
    assert len(session.messages) == 1


@pytest.mark.asyncio
async def test_scoped_setup_unload_and_restart_remove_and_restore_single_contributions(
    tmp_path: Path,
):
    root = tmp_path / "plugins"
    root.mkdir()
    _ = stage_plugin_package(Path(__file__).resolve().parents[1], root / "plugin_undo")
    manager = SessionManager(tmp_path / "workspace")
    kernel = PluginKernel(
        [root],
        services=HostServices(
            event_bus=EventBus(), session_manager=manager, memory_engine=_MemoryEngine()
        ),
    )
    await kernel.load_all()
    try:
        for _ in range(2):
            assert [module.slot for module in kernel.before_turn_modules] == [
                "plugin_undo.undo"
            ]
            assert kernel.bot_commands == [("undo", "撤销上一轮对话")]
            # Exercise the actual dynamically loaded v2 contribution as well.
            frame = SimpleNamespace(
                input=SimpleNamespace(
                    session_key="cli:1",
                    msg=SimpleNamespace(
                        content="/undo",
                        channel="cli",
                        chat_id="1",
                        timestamp=datetime.now(),
                    ),
                ),
                slots={"session:session": manager.get_or_create("cli:1")},
            )
            await kernel.before_turn_modules[0].run(frame)
            assert frame.slots["session:ctx"].abort_reply == "没有可撤销的上一轮对话。"
            assert await kernel.unload("plugin_undo") == []
            assert kernel.before_turn_modules == []
            assert kernel.bot_commands == []
            assert await kernel.load("plugin_undo") is True
    finally:
        await kernel.unload("plugin_undo")


@pytest.mark.asyncio
@pytest.mark.parametrize("content,has_context", [("/help", False), ("/undo", True)])
async def test_undo_ignores_unrelated_or_already_handled_commands(
    tmp_path, content, has_context
):
    manager = SessionManager(tmp_path)
    memory = _MemoryEngine()
    module = UndoCommandModule(PluginUndo(manager, memory))
    sentinel = object()
    slots = {"session:ctx": sentinel} if has_context else {}
    frame = SimpleNamespace(
        input=SimpleNamespace(msg=SimpleNamespace(content=content)), slots=slots
    )

    assert await module.run(frame) is frame
    assert slots == ({"session:ctx": sentinel} if has_context else {})
    assert memory.calls == []
