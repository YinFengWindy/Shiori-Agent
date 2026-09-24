from __future__ import annotations

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from shiori_plugin_testkit.packages import stage_plugin_package

from agent.plugin_host import HostServices, PluginKernel
from bus.event_bus import EventBus
from plugins.setup_helper.backend.plugin import ChatIdCommandModule

PLUGIN_DIR = Path(__file__).resolve().parents[1]


def _state(
    content: str, *, chat_id: str = "42", channel: str = "telegram"
) -> SimpleNamespace:
    return SimpleNamespace(
        session_key=f"{channel}:{chat_id}",
        msg=SimpleNamespace(
            content=content,
            channel=channel,
            chat_id=chat_id,
            timestamp=datetime.now(),
        ),
    )


@pytest.mark.asyncio
async def test_chatid_command_aborts_with_chat_id_reply() -> None:
    module = ChatIdCommandModule()
    frame = SimpleNamespace(input=_state("/chatid"), slots={})

    result = await module.run(frame)

    ctx = result.slots["session:ctx"]
    assert ctx.abort is True
    assert "42" in ctx.abort_reply
    assert 'channel = "telegram"' in ctx.abort_reply


@pytest.mark.asyncio
async def test_myid_alias_also_matches() -> None:
    module = ChatIdCommandModule()
    frame = SimpleNamespace(input=_state("/myid"), slots={})

    result = await module.run(frame)

    assert result.slots["session:ctx"].abort is True


@pytest.mark.asyncio
async def test_unrelated_command_is_ignored() -> None:
    module = ChatIdCommandModule()
    frame = SimpleNamespace(input=_state("/help"), slots={})

    result = await module.run(frame)

    assert "session:ctx" not in result.slots


@pytest.mark.asyncio
async def test_setup_contributes_before_turn_module_and_bot_command_via_kernel(
    tmp_path: Path,
) -> None:
    """setup(ctx) 必须与旧 SetupHelper 的 before_turn_modules/bot_commands 等价。

    用真实 PluginKernel 装配真实插件目录来验证，而不是自造 fake capability——
    fake 与真实 capability 契约脱钩，capability 改坏也不会让测试变红（#182 评审）。
    """
    root = tmp_path / "plugins"
    root.mkdir()
    stage_plugin_package(PLUGIN_DIR, root / "setup_helper")
    kernel = PluginKernel([root], services=HostServices(event_bus=EventBus()))
    await kernel.load_all()

    assert [type(m).__name__ for m in kernel.before_turn_modules] == [
        "ChatIdCommandModule"
    ]
    assert kernel.bot_commands == [("chatid", "查看我的 chat_id（配置 proactive 用）")]

    # 卸载后贡献必须整体撤回，证明 phase 槽位与 bot 命令都真正挂在插件作用域上
    _ = await kernel.unload("setup_helper")
    assert kernel.before_turn_modules == []
    assert kernel.bot_commands == []
