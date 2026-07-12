from __future__ import annotations

import json
import shutil
import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from agent.core.response_parser import ResponseMetadata
from agent.lifecycle.types import AfterReasoningCtx, PromptRenderCtx
from agent.plugins.context import PluginContext, PluginKVStore
from agent.plugins.manager import PluginManager
from agent.plugins.registry import plugin_registry
from bus.event_bus import EventBus
from core.roles import RoleStore


def _load_meme_plugin_module() -> Any:
    path = Path(__file__).parents[1] / "plugins" / "meme" / "plugin.py"
    spec = importlib.util.spec_from_file_location(
        "test_meme_plugin",
        path,
        submodule_search_locations=[str(path.parent)],
    )
    if spec is None or spec.loader is None:
        raise ImportError(str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_meme_plugin_module = _load_meme_plugin_module()
MemePlugin = _meme_plugin_module.MemePlugin
MemePromptModule = _meme_plugin_module.MemePromptModule


@pytest.fixture(autouse=True)
def _clean_registry():
    plugin_registry._handlers._handlers.clear()
    plugin_registry._classes.clear()
    plugin_registry._instances.clear()
    yield
    plugin_registry._handlers._handlers.clear()
    plugin_registry._classes.clear()
    plugin_registry._instances.clear()


def _write_meme_workspace(workspace: Path) -> Path:
    memes = workspace / "memes"
    (memes / "shy").mkdir(parents=True)
    image = memes / "shy" / "001.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n")
    (memes / "manifest.json").write_text(
        json.dumps(
            {"categories": {"shy": {"desc": "害羞", "enabled": True}}},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return image


async def _make_plugin(
    tmp_path: Path,
    *,
    app_config: object | None = None,
    session_manager: object | None = None,
) -> MemePlugin:
    plugin_dir = tmp_path / "plugins" / "meme"
    plugin_dir.mkdir(parents=True)
    plugin = MemePlugin()
    plugin.context = PluginContext(
        event_bus=None,
        tool_registry=None,
        plugin_id="meme",
        plugin_dir=plugin_dir,
        kv_store=PluginKVStore(plugin_dir / ".kv.json"),
        workspace=tmp_path,
        app_config=app_config,
        session_manager=session_manager,
    )
    await plugin.initialize()
    return plugin


@pytest.mark.asyncio
async def test_meme_prompt_module_injects_bottom_section(tmp_path: Path) -> None:
    _write_meme_workspace(tmp_path)
    plugin = await _make_plugin(tmp_path)
    module = plugin.prompt_render_modules()[0]
    assert isinstance(module, MemePromptModule)

    ctx = PromptRenderCtx(
        session_key="telegram:1",
        channel="telegram",
        chat_id="1",
        content="你好",
        media=None,
        timestamp=datetime.now(timezone.utc),
        history=[],
        skill_names=[],
        retrieved_memory_block="",
        disabled_sections=set(),
        turn_injection_prompt="",
    )
    frame = SimpleNamespace(slots={"prompt:ctx": ctx})

    await module.run(frame)

    assert ctx.system_sections_bottom[0].name == "memes"
    assert "<meme:shy>" in ctx.system_sections_bottom[0].content


@pytest.mark.asyncio
async def test_plugin_manager_collects_meme_prompt_module_before_initialize(tmp_path: Path) -> None:
    _write_meme_workspace(tmp_path)
    plugin_dir = tmp_path / "plugin_src" / "meme"
    shutil.copytree(Path(__file__).parents[1] / "plugins" / "meme", plugin_dir)
    manager = PluginManager(
        [plugin_dir.parent],
        event_bus=EventBus(),
        workspace=tmp_path,
    )

    await manager.load_all()

    assert manager.loaded_count == 1
    assert len(manager.prompt_render_modules) == 1


@pytest.mark.asyncio
async def test_meme_plugin_decorates_after_reasoning(tmp_path: Path) -> None:
    image = _write_meme_workspace(tmp_path)
    plugin = await _make_plugin(tmp_path)
    ctx = AfterReasoningCtx(
        session_key="telegram:1",
        channel="telegram",
        chat_id="1",
        tools_used=(),
        thinking=None,
        response_metadata=ResponseMetadata(raw_text="好的 <meme:shy>"),
        streamed=False,
        tool_chain=(),
        context_retry={},
        reply="好的 <meme:shy>",
    )

    out = await plugin.decorate_meme(ctx)

    assert out.reply == "好的"
    assert out.media == [str(image)]
    assert out.meme_tag == "shy"


@pytest.mark.asyncio
async def test_meme_plugin_strips_empty_protocol_tag(tmp_path: Path) -> None:
    _write_meme_workspace(tmp_path)
    plugin = await _make_plugin(tmp_path)
    ctx = AfterReasoningCtx(
        session_key="telegram:1",
        channel="telegram",
        chat_id="1",
        tools_used=(),
        thinking=None,
        response_metadata=ResponseMetadata(raw_text="好的 <meme:>"),
        streamed=False,
        tool_chain=(),
        context_retry={},
        reply="好的 <meme:>",
    )

    out = await plugin.decorate_meme(ctx)

    assert out.reply == "好的"
    assert out.media == []
    assert out.meme_tag is None


@pytest.mark.asyncio
async def test_role_reactions_use_sendable_assets_and_global_emoji(tmp_path: Path) -> None:
    image = tmp_path / "reaction.png"
    image.write_bytes(b"reaction")
    role_store = RoleStore(tmp_path)
    role_store.create_role(name="Mira", system_prompt="mira", role_id="mira")
    role = role_store.update_role(
        "mira",
        asset_categories=[
            {"id": "default", "name": "默认"},
            {"id": "reactions", "name": "表情包", "allow_role_send": True},
        ],
        illustration_sources=[image],
        illustration_category_id="reactions",
    )
    session_manager = SimpleNamespace(
        get_or_create=lambda _key: SimpleNamespace(metadata={"role_id": "mira"})
    )
    plugin = await _make_plugin(tmp_path, session_manager=session_manager)
    prompt_ctx = PromptRenderCtx(
        session_key="role:mira",
        channel="desktop",
        chat_id="role:mira",
        content="你好",
        media=None,
        timestamp=datetime.now(timezone.utc),
        history=[],
        skill_names=[],
        retrieved_memory_block="",
        disabled_sections=set(),
        turn_injection_prompt="",
        session_metadata={"role_id": "mira"},
    )

    await plugin.prompt_render_modules()[0].run(
        SimpleNamespace(slots={"prompt:ctx": prompt_ctx})
    )
    prompt = prompt_ctx.system_sections_bottom[0].content
    assert "<meme:分类ID>" in prompt
    assert "reactions: 表情包" in prompt
    assert "heart: ❤️" in prompt

    ctx = AfterReasoningCtx(
        session_key="role:mira",
        channel="desktop",
        chat_id="role:mira",
        tools_used=(),
        thinking=None,
        response_metadata=ResponseMetadata(raw_text="喜欢 <emoji:heart> <meme:reactions>"),
        streamed=False,
        tool_chain=(),
        context_retry={},
        reply="喜欢 <emoji:heart> <meme:reactions>",
    )
    out = await plugin.decorate_meme(ctx)

    assert out.reply == "喜欢 ❤️"
    assert out.media == [str(tmp_path / "roles" / role.illustrations[0])]
    assert out.meme_tag == "reactions"


@pytest.mark.asyncio
async def test_role_reactions_reject_disabled_category_and_unknown_emoji(tmp_path: Path) -> None:
    image = tmp_path / "reaction.png"
    image.write_bytes(b"reaction")
    store = RoleStore(tmp_path)
    store.create_role(name="Mira", system_prompt="mira", role_id="mira")
    store.update_role(
        "mira",
        asset_categories=[
            {"id": "default", "name": "默认"},
            {"id": "private", "name": "私有", "allow_role_send": False},
        ],
        illustration_sources=[image],
        illustration_category_id="private",
    )
    plugin = await _make_plugin(
        tmp_path,
        session_manager=SimpleNamespace(
            get_or_create=lambda _key: SimpleNamespace(metadata={"role_id": "mira"})
        ),
    )
    ctx = AfterReasoningCtx(
        session_key="role:mira",
        channel="desktop",
        chat_id="role:mira",
        tools_used=(),
        thinking=None,
        response_metadata=ResponseMetadata(raw_text="好 <emoji:unknown> <meme:private>"),
        streamed=False,
        tool_chain=(),
        context_retry={},
        reply="好 <emoji:unknown> <meme:private>",
    )

    out = await plugin.decorate_meme(ctx)

    assert out.reply == "好"
    assert out.media == []
