"""Package-local loaders and real host fixtures for status_commands tests."""

from __future__ import annotations
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
import pytest
from shiori_sdk.testing.packages import plugin_directory, stage_plugin_package
from agent.core.passive_turn import ContextStore
from agent.lifecycle.phases.before_turn import (
    BeforeTurnFrame,
    default_before_turn_modules,
)
from agent.lifecycle.types import TurnState
from agent.plugin_host import HostServices, PluginKernel
from bus.event_bus import EventBus
from shiori_sdk.messages import InboundMessage
from session.manager import Session
import asyncio
import sys
from agent.plugin_host import kernel as kernel_module
from agent.plugin_host.capabilities import BotCommandsCapability
from shiori_sdk.memory.committed import TurnCommitted

PLUGIN_ROOT = plugin_directory("status_commands")


@pytest.fixture
def kernel_factory(tmp_path: Path):
    @asynccontextmanager
    async def start(
        *,
        observe: str = "missing",
        plugin_source: Path = PLUGIN_ROOT,
        observe_source: Path | None = None,
    ):
        root = tmp_path / "plugins"
        stage_plugin_package(plugin_source, root / "status_commands")
        if observe != "missing":
            provider = (
                observe_source
                if observe_source is not None
                else plugin_directory("observe")
            )
            stage_plugin_package(provider, root / "observe")
            if observe in {"failed", "unexported"}:
                body = (
                    "raise RuntimeError('observe setup failed')"
                    if observe == "failed"
                    else "pass"
                )
                _ = (root / "observe/backend/plugin.py").write_text(
                    f"async def setup(ctx):\n    {body}\n",
                    encoding="utf-8",
                )
        bus = EventBus()
        kernel = PluginKernel(
            [root],
            namespace="status_integration",
            services=HostServices(
                event_bus=bus,
                workspace=tmp_path / "workspace",
                plugin_configs={"observe": {"enabled": observe != "disabled"}},
            ),
        )
        try:
            await kernel.load_all()
            yield kernel, bus
        finally:
            await kernel.terminate_all()

    return start


@pytest.fixture
def command_frame():
    def make(content: str, session: Session | None = None):
        session = session or Session(key="telegram:1")
        return BeforeTurnFrame(
            input=TurnState(
                msg=InboundMessage(
                    channel="telegram", sender="user", chat_id="1", content=content
                ),
                session_key=session.key,
                dispatch_outbound=True,
                session=session,
            ),
            slots={"session:session": session},
        )

    return make


@pytest.fixture
def run_command(command_frame):
    async def run(kernel: PluginKernel, bus: EventBus, content: str):
        frame = command_frame(content)
        session = frame.input.session
        manager = MagicMock(get_or_create=MagicMock(return_value=session))
        context_store = MagicMock(spec=ContextStore, prepare=AsyncMock())
        for module in default_before_turn_modules(
            bus,
            manager,
            context_store,
            plugin_modules=kernel.before_turn_modules,
        ):
            frame = await module.run(frame)
        assert frame.output is not None and frame.output.abort
        context_store.prepare.assert_not_awaited()
        assert frame.input.session is session
        assert session is not None and session.messages == []
        return frame.output.abort_reply

    return run


"""Real v2 assembly and optional-provider lifecycle for status commands."""


_COMMANDS = [("memorystatus", "查看记忆整理状态"), ("kvcache", "查看 KVCache 状态")]


@pytest.mark.asyncio
@pytest.mark.parametrize("plugin_id", ["status_commands", "observe"])
async def test_kernel_staging_excludes_package_virtual_environments(
    tmp_path: Path, kernel_factory, run_command, plugin_id: str
):
    original = (
        plugin_directory("status_commands")
        if plugin_id == "status_commands"
        else plugin_directory("observe")
    )
    source = stage_plugin_package(original, tmp_path / "source" / plugin_id)
    for name in (".venv", "custom-python"):
        environment = source / name
        environment.mkdir()
        _ = (environment / "pyvenv.cfg").write_text(
            "home = local-test\n", encoding="utf-8"
        )
        _ = (environment / "environment-only.txt").write_text(
            "not a plugin asset", encoding="utf-8"
        )
    options = (
        {"plugin_source": source}
        if plugin_id == "status_commands"
        else {"observe": "active", "observe_source": source}
    )

    async with kernel_factory(**options) as (kernel, bus):
        staged = next(
            record.plugin_dir
            for record in kernel.discover()
            if record.name == plugin_id
        )
        assert not (staged / ".venv").exists()
        assert not (staged / "custom-python").exists()
        assert (source / ".venv" / "pyvenv.cfg").is_file()
        assert (source / "custom-python" / "pyvenv.cfg").is_file()
        assert kernel.bot_commands == _COMMANDS
        assert "还没有完成过记忆整理" in await run_command(kernel, bus, "/memorystatus")
        cache_reply = await run_command(kernel, bus, "/kvcache")
        if plugin_id == "observe":
            assert cache_reply == "暂无 KVCache 数据。"
        else:
            assert "KVCache 不可用" in cache_reply


@pytest.mark.asyncio
@pytest.mark.parametrize("observe", ["missing", "disabled", "failed", "unexported"])
async def test_status_commands_stay_active_without_observe(
    kernel_factory, run_command, observe
):
    async with kernel_factory(observe=observe) as (kernel, bus):
        record = next(
            record for record in kernel.discover() if record.name == "status_commands"
        )
        assert record.manifest.api == 2
        assert record.manifest.dependencies == ()
        assert record.manifest.optional_dependencies == ("observe",)
        assert set(record.manifest.capabilities) == {
            "lifecycle",
            "bot_commands",
            "dependencies",
        }
        assert kernel.bot_commands == _COMMANDS
        assert "还没有完成过记忆整理" in await run_command(kernel, bus, "/memorystatus")
        assert "KVCache 不可用" in await run_command(kernel, bus, "/kvcache")


def _owns(import_path: str, module_name: str) -> bool:
    return module_name == import_path or module_name.startswith(import_path + ".")


@pytest.mark.asyncio
@pytest.mark.parametrize("observe", ["missing", "disabled"])
async def test_unavailable_provider_implementation_is_never_imported(
    kernel_factory, run_command, monkeypatch, observe
):
    """The kernel imports plugin entries as ``akasic_plugin_{namespace}_{id}``.

    Spy on that real import call and on ``sys.modules``: the consumer must be
    imported under its kernel path while the optional provider never is.
    """
    consumer = "akasic_plugin_status_integration_status_commands"
    provider = "akasic_plugin_status_integration_observe"
    for name in tuple(sys.modules):
        if _owns(provider, name) or _owns("plugins.observe", name):
            monkeypatch.delitem(sys.modules, name)
    imported: list[str] = []
    original_import = kernel_module._import_module

    def record_import(module_name, *args, **kwargs):
        imported.append(module_name)
        return original_import(module_name, *args, **kwargs)

    monkeypatch.setattr(kernel_module, "_import_module", record_import)
    async with kernel_factory(observe=observe) as (kernel, bus):
        assert "KVCache 不可用" in await run_command(kernel, bus, "/kvcache")
        loaded = set(sys.modules)

    assert imported == [consumer]
    assert any(_owns(consumer, name) for name in loaded)
    assert not any(
        _owns(provider, name) or _owns("plugins.observe", name) for name in loaded
    )


@pytest.mark.asyncio
async def test_real_observe_writer_and_provider_reload_use_current_api(
    kernel_factory, run_command
):
    async with kernel_factory(observe="active") as (kernel, bus):
        assert await run_command(kernel, bus, "/kvcache") == "暂无 KVCache 数据。"
        modules = kernel.before_turn_modules
        first_api = kernel._dependency_api("observe")
        event = TurnCommitted(
            session_key="telegram:1",
            channel="telegram",
            chat_id="1",
            input_message="hi",
            persisted_user_message="hi",
            assistant_response="真实回复",
            tools_used=[],
            react_stats={"cache_prompt_tokens": 1000, "cache_hit_tokens": 800},
        )
        await bus.emit(event)
        async with asyncio.timeout(5):
            while not first_api.recent_cache_turns("telegram:1"):
                await asyncio.sleep(0.01)
        # Wording and layout belong to the plugin tests; here only the real
        # writer's committed turn must reach the consumer through the export.
        assert "真实回复" in await run_command(kernel, bus, "/KVCACHE@MyBot 1")
        assert await kernel.unload("observe") == []
        assert kernel.before_turn_modules == modules
        assert kernel.bot_commands == _COMMANDS
        assert "KVCache 不可用" in await run_command(kernel, bus, "/kvcache")
        assert await kernel.load("observe")
        assert kernel._dependency_api("observe") is not first_api
        # Make a changed export observable without re-registering the consumer.
        current_api = kernel._dependency_api("observe")
        current_api.recent_cache_turns = lambda *_args, **_kwargs: ()
        assert await run_command(kernel, bus, "/kvcache") == "暂无 KVCache 数据。"
        assert kernel.before_turn_modules == modules


@pytest.mark.asyncio
async def test_repeated_status_enable_and_unload_have_no_duplicate_contributions(
    kernel_factory, run_command
):
    async with kernel_factory() as (kernel, bus):
        for _ in range(3):
            assert await kernel.load("status_commands")
            assert kernel.bot_commands == _COMMANDS
            assert len(kernel.before_turn_modules) == 2
            assert "KVCache 不可用" in await run_command(kernel, bus, "/kvcache")
            assert await kernel.unload("status_commands") == []
            assert kernel.bot_commands == []
            assert kernel.before_turn_modules == []
            assert await kernel.load("status_commands")


@pytest.mark.asyncio
async def test_partial_setup_failure_rolls_back_modules_and_commands(
    kernel_factory, monkeypatch
):
    original_add = BotCommandsCapability.add

    def fail_after_registration(self, command, description):
        original_add(self, command, description)
        if command == "kvcache":
            raise RuntimeError("failed after command registration")

    with monkeypatch.context() as patch:
        patch.setattr(BotCommandsCapability, "add", fail_after_registration)
        async with kernel_factory() as (kernel, _):
            assert kernel.states()[0]["state"] == "FAILED"
            assert kernel.before_turn_modules == []
            assert kernel.bot_commands == []
            patch.undo()
            assert await kernel.load("status_commands")
            assert kernel.bot_commands == _COMMANDS
            assert len(kernel.before_turn_modules) == 2
