"""Undo command business outcomes through SDK session and memory ports."""

import pytest
from plugins.plugin_undo.backend.plugin import PluginUndo, UndoCommandModule, setup
from shiori_sdk.commands import CommandInput
from shiori_sdk.sessions import UndoSessionResult
from shiori_sdk.testing.commands import FakeCommandFrame, FakeSessionUndo
from shiori_sdk.testing.extensions import FakeExtensionContext


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
@pytest.mark.parametrize("failure", [False, True])
async def test_preview_then_session_delete_then_memory_cleanup(failure, caplog):
    manager = FakeSessionUndo(
        UndoSessionResult(["cli:1:0", "cli:1:1"], "cli:1:0", "cli:1:1", 0, 2, 0)
    )
    memory = _MemoryEngine(fail_real_undo=failure)
    frame = FakeCommandFrame(CommandInput(" /UNDO@Bot ", "cli:1"))
    await UndoCommandModule(PluginUndo(manager, memory)).run(frame)
    result = frame.slots["session:ctx"]
    assert result.abort
    assert manager.deleted
    assert manager.rollback_sources == ["cli:1:0", "cli:1:1", "cli:1:2"]
    assert [c["dry_run"] for c in memory.calls] == [True, False]
    assert "已撤销上一轮对话" in result.abort_reply
    assert ("记忆清理失败" in result.abort_reply) == failure
    assert "删除消息：2 条" in result.abort_reply
    if failure:
        assert "deleted_ids=['cli:1:0', 'cli:1:1']" in caplog.text
        assert "'affected_ids': ['mem1']" in caplog.text
    else:
        assert "失效记忆：1 条" in result.abort_reply
        assert "恢复旧记忆：1 条" in result.abort_reply


@pytest.mark.asyncio
async def test_preview_failure_prevents_session_deletion():
    manager = FakeSessionUndo(UndoSessionResult(["u", "a"], "u", "a", 0, 0, 0))

    class BrokenMemory(_MemoryEngine):
        def undo_by_message_sources(self, message_ids, *, dry_run=False):
            raise RuntimeError("preview failed")

    with pytest.raises(RuntimeError, match="preview failed"):
        await PluginUndo(manager, BrokenMemory()).undo("cli:1")
    assert not manager.deleted


@pytest.mark.asyncio
async def test_no_passive_turn_does_not_touch_memory():
    memory = _MemoryEngine()
    assert (
        await PluginUndo(FakeSessionUndo(), memory).undo("cli:1")
        == "没有可撤销的上一轮对话。"
    )
    assert memory.calls == []


@pytest.mark.asyncio
async def test_missing_memory_still_undoes_session():
    manager = FakeSessionUndo(UndoSessionResult(["u", "a"], "u", "a", 0, 0, 0))
    assert "失效记忆：0 条" in await PluginUndo(manager, None).undo("cli:1")


@pytest.mark.asyncio
async def test_setup_and_unload_register_one_command_and_module():
    ctx = FakeExtensionContext("plugin_undo", session_manager=FakeSessionUndo())
    await setup(ctx)
    assert ctx.bot_commands.commands == [("undo", "撤销上一轮对话")]
    assert len(ctx.lifecycle.modules["before_turn"]) == 1
    await ctx.aclose()
    assert not ctx._lifecycle.modules and not ctx.bot_commands.commands


@pytest.mark.asyncio
@pytest.mark.parametrize("content,prior", [("/help", False), ("/undo", True)])
async def test_unrelated_and_previously_handled_commands_are_untouched(content, prior):
    manager = FakeSessionUndo()
    frame = FakeCommandFrame(CommandInput(content, "cli:1"))
    sentinel = object()
    if prior:
        frame.slots["session:ctx"] = sentinel
    await UndoCommandModule(PluginUndo(manager, None)).run(frame)
    assert manager.calls == []
    assert frame.slots == ({"session:ctx": sentinel} if prior else {})
