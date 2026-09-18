from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from shiori_plugin_testkit.packages import plugin_directory, stage_plugin_package

from agent.core.response_parser import ResponseMetadata
from agent.core.runtime_support import TurnRunResult
from agent.looping.ports import SessionServices
from agent.lifecycle.phases.after_reasoning import (
    AfterReasoningFrame,
    default_after_reasoning_modules,
)
from agent.lifecycle.phases.prompt_render import default_prompt_render_modules
from agent.lifecycle.types import (
    AfterReasoningCtx,
    AfterReasoningInput,
    PromptRenderCtx,
    TurnState,
)
from agent.plugin_host import HostServices, PluginKernel
from agent.plugin_host.events import ScopedEventBus
from bus.event_bus import EventBus
from bus.events import InboundMessage
from core.roles import RoleStore
from session.manager import Session

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
_KernelLoader = Callable[..., Awaitable[tuple[PluginKernel, EventBus]]]


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
    return workspace / "plugin-data" / "meme" / "library" / "shy" / "001.png"


@pytest_asyncio.fixture
async def load_kernel() -> AsyncIterator[_KernelLoader]:
    kernels: list[PluginKernel] = []

    async def start(tmp_path: Path, **kwargs: Any):
        kernel, bus = await _load_kernel(tmp_path, **kwargs)
        kernels.append(kernel)
        return kernel, bus

    yield start
    for kernel in reversed(kernels):
        await kernel.terminate_all()


async def _load_kernel(
    tmp_path: Path,
    *,
    session_manager: object | None = None,
    citation: str = "active",
    plugin_source: Path = PLUGIN_ROOT,
):
    root = tmp_path / "plugins"
    stage_plugin_package(plugin_source, root / "meme")
    if citation != "missing":
        stage_plugin_package(plugin_directory("citation"), root / "citation")
        if citation == "failed":
            (root / "citation" / "backend" / "plugin.py").write_text(
                'async def setup(ctx):\n    raise RuntimeError("citation failed")\n',
                encoding="utf-8",
            )
    bus = EventBus()
    kernel = PluginKernel(
        [root],
        services=HostServices(
            event_bus=bus,
            plugin_configs={"citation": {"enabled": citation != "disabled"}},
            workspace=tmp_path,
            session_manager=session_manager,
        ),
    )
    await kernel.load_all()
    return kernel, bus


@pytest.mark.asyncio
async def test_meme_prompt_module_injects_bottom_section(
    tmp_path: Path, load_kernel: _KernelLoader
) -> None:
    _write_meme_workspace(tmp_path)
    kernel, bus = await load_kernel(tmp_path)
    module = kernel.prompt_render_modules[-1]
    assert type(module).__name__ == "MemePromptModule"

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
    ordered = default_prompt_render_modules(
        bus, MagicMock(), kernel.prompt_render_modules
    )
    names = [type(item).__name__ for item in ordered]
    assert names.index("CitationPromptModule") < names.index("MemePromptModule")


@pytest.mark.asyncio
async def test_meme_discovery_uses_v2_and_declares_citation(
    tmp_path: Path, load_kernel: _KernelLoader
) -> None:
    kernel, _ = await load_kernel(tmp_path)
    record = next(record for record in kernel.discover() if record.name == "meme")
    assert record.manifest.api == 2
    assert record.manifest.dependencies == ("citation",)
    assert set(record.manifest.capabilities) == {
        "lifecycle",
        "events",
        "workspace",
        "session_manager",
    }
    assert kernel.loaded_count == 2
    assert [type(module).__name__ for module in kernel.prompt_render_modules] == [
        "CitationPromptModule",
        "MemePromptModule",
    ]
    await kernel.terminate_all()


@pytest.mark.asyncio
async def test_meme_kernel_staging_excludes_package_virtual_environments(
    tmp_path: Path, load_kernel: _KernelLoader
) -> None:
    source = stage_plugin_package(PLUGIN_ROOT, tmp_path / "source" / "meme")
    for name in (".venv", "custom-python"):
        environment = source / name
        environment.mkdir()
        _ = (environment / "pyvenv.cfg").write_text(
            "home = local-test\n", encoding="utf-8"
        )
        _ = (environment / "environment-only.txt").write_text(
            "not a plugin asset", encoding="utf-8"
        )
    workspace = tmp_path / "workspace"
    image = _write_meme_workspace(workspace)

    kernel, bus = await load_kernel(workspace, plugin_source=source)

    assert kernel.loaded_count == 2
    staged = next(
        record.plugin_dir for record in kernel.discover() if record.name == "meme"
    )
    assert not (staged / ".venv").exists()
    assert not (staged / "custom-python").exists()
    assert (source / ".venv" / "pyvenv.cfg").is_file()
    assert (source / "custom-python" / "pyvenv.cfg").is_file()
    assert (await bus.emit(_reply_ctx())).media == [str(image)]


@pytest.mark.asyncio
async def test_meme_plugin_decorates_after_reasoning(
    tmp_path: Path, load_kernel: _KernelLoader
) -> None:
    image = _write_meme_workspace(tmp_path)
    kernel, bus = await load_kernel(tmp_path)
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

    out = await bus.emit(ctx)

    assert out.reply == "好的"
    assert out.media == [str(image)]
    assert out.meme_tag == "shy"


@pytest.mark.asyncio
async def test_meme_plugin_strips_empty_protocol_tag(
    tmp_path: Path, load_kernel: _KernelLoader
) -> None:
    _write_meme_workspace(tmp_path)
    kernel, bus = await load_kernel(tmp_path)
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

    out = await bus.emit(ctx)

    assert out.reply == "好的"
    assert out.media == []
    assert out.meme_tag is None


@pytest.mark.asyncio
async def test_role_reactions_use_sendable_assets_and_global_emoji(
    tmp_path: Path,
    load_kernel: _KernelLoader,
) -> None:
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
    kernel, bus = await load_kernel(tmp_path, session_manager=session_manager)
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

    await kernel.prompt_render_modules[-1].run(
        SimpleNamespace(slots={"prompt:ctx": prompt_ctx})
    )
    prompt = prompt_ctx.system_sections_bottom[0].content
    assert "<meme:分类ID>" in prompt
    assert "reactions: 表情包" in prompt
    assert "heart: ❤️" in prompt

    out, session = await _run_reply(
        kernel,
        bus,
        "喜欢 [§mem_1]\n§cited:[mem_1]§ <emoji:heart> <emoji:unknown> <meme:reactions> <foo:bar>",
        role_id="mira",
    )

    assert out.reply == "喜欢 ❤️"
    assert out.media == [str(tmp_path / "roles" / role.illustrations[0])]
    assert out.meme_tag == "reactions"
    assert session.messages[-1]["content"] == "喜欢 ❤️"
    assert session.messages[-1]["cited_memory_ids"] == ["mem_1"]
    assert session.messages[-1]["media"] == out.media


@pytest.mark.asyncio
async def test_role_reactions_reject_disabled_category_and_unknown_emoji(
    tmp_path: Path,
    load_kernel: _KernelLoader,
) -> None:
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
    kernel, bus = await load_kernel(
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
        response_metadata=ResponseMetadata(
            raw_text="好 <emoji:unknown> <meme:private>"
        ),
        streamed=False,
        tool_chain=(),
        context_retry={},
        reply="好 <emoji:unknown> <meme:private>",
    )

    out = await bus.emit(ctx)

    assert out.reply == "好"
    assert out.media == []


async def _run_reply(kernel: PluginKernel, bus: EventBus, reply: str, *, role_id: str):
    session = Session(key="role:mira", metadata={"role_id": role_id})
    services = SessionServices(
        session_manager=MagicMock(append_messages=AsyncMock()),
    )
    frame = AfterReasoningFrame(
        input=AfterReasoningInput(
            state=TurnState(
                msg=InboundMessage(
                    channel="desktop",
                    sender="user",
                    chat_id="role:mira",
                    content="你好",
                ),
                session_key=session.key,
                dispatch_outbound=True,
                session=session,
            ),
            turn_result=TurnRunResult(reply=reply),
        ),
    )
    for module in default_after_reasoning_modules(
        bus,
        services,
        plugin_modules=kernel.after_reasoning_modules,
    ):
        frame = await module.run(frame)
    assert frame.output is not None
    assert frame.output.outbound.content == frame.output.ctx.reply
    assert frame.output.outbound.media == frame.output.ctx.media
    return frame.output.ctx, session


def _reply_ctx():
    return AfterReasoningCtx(
        session_key="telegram:1",
        channel="telegram",
        chat_id="1",
        reply="好的 <meme:shy>",
        response_metadata=ResponseMetadata(raw_text="好的 <meme:shy>"),
        tools_used=(),
        thinking=None,
        streamed=False,
        tool_chain=(),
        context_retry={},
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("citation", ["missing", "disabled", "failed"])
async def test_meme_blocks_when_citation_is_unavailable(
    tmp_path: Path, load_kernel: _KernelLoader, citation: str
):
    kernel, bus = await load_kernel(tmp_path, citation=citation)
    state = next(item for item in kernel.states() if item["id"] == "meme")
    assert state["state"] == "BLOCKED"
    assert "citation" in state["error"]
    assert kernel.prompt_render_modules == []
    assert kernel.after_reasoning_modules == []
    assert (await bus.emit(_reply_ctx())).reply == "好的 <meme:shy>"


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["meme", "citation"])
async def test_meme_unload_and_reload_removes_all_contributions(
    tmp_path: Path, load_kernel: _KernelLoader, provider: str
):
    image = _write_meme_workspace(tmp_path)
    kernel, bus = await load_kernel(tmp_path)
    for _ in range(3):
        # Loading an active plugin again must not install a second handler.
        assert await kernel.load("meme")
        decorated = await bus.emit(_reply_ctx())
        assert decorated.reply == "好的"
        assert decorated.media == [str(image)]
        assert decorated.meme_tag == "shy"
        assert len(kernel.prompt_render_modules) == 2
        assert await kernel.unload(provider) == []
        assert not any(
            type(module).__name__ == "MemePromptModule"
            for module in kernel.prompt_render_modules
        )
        untouched = await bus.emit(_reply_ctx())
        assert untouched.reply == "好的 <meme:shy>"
        assert untouched.media == []
        assert await kernel.load("meme")
    await kernel.terminate_all()
    assert kernel.prompt_render_modules == []
    assert kernel.after_reasoning_modules == []
    assert (await bus.emit(_reply_ctx())).reply == "好的 <meme:shy>"


@pytest.mark.asyncio
async def test_meme_setup_failure_rolls_back_events_and_prompt(
    tmp_path: Path, load_kernel: _KernelLoader, monkeypatch: pytest.MonkeyPatch
):
    image = _write_meme_workspace(tmp_path)
    original_on = ScopedEventBus.on

    def fail_after_subscription(self: ScopedEventBus, event_type: type, handler: Any):
        original_on(self, event_type, handler)
        raise RuntimeError("registration failed after event effect")

    with monkeypatch.context() as patch:
        patch.setattr(ScopedEventBus, "on", fail_after_subscription)
        kernel, bus = await load_kernel(tmp_path)
    state = next(item for item in kernel.states() if item["id"] == "meme")
    assert state["state"] == "FAILED"
    assert state["error"] == "registration failed after event effect"
    assert [type(module).__name__ for module in kernel.prompt_render_modules] == [
        "CitationPromptModule"
    ]
    assert (await bus.emit(_reply_ctx())).reply == "好的 <meme:shy>"
    assert await kernel.load("meme")
    decorated = await bus.emit(_reply_ctx())
    assert decorated.media == [str(image)]
    assert decorated.meme_tag == "shy"
    assert len(kernel.prompt_render_modules) == 2
    await kernel.terminate_all()
