"""Real v2 assembly and optional-provider lifecycle for status commands."""

from __future__ import annotations

import asyncio
import builtins
from pathlib import Path

import pytest
from shiori_plugin_testkit.packages import plugin_directory, stage_plugin_package

from agent.plugin_host.capabilities import BotCommandsCapability
from bus.events_lifecycle import TurnCommitted

_COMMANDS = [("memorystatus", "查看记忆整理状态"), ("kvcache", "查看 KVCache 状态")]


@pytest.mark.asyncio
@pytest.mark.parametrize("plugin_id", ["status_commands", "observe"])
async def test_kernel_staging_excludes_package_virtual_environments(
    tmp_path: Path, kernel_factory, run_command, plugin_id: str
):
    original = (
        Path(__file__).resolve().parents[1]
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
        assert (
            await run_command(kernel, bus, "/kvcache")
            == "KVCache 不可用（observe 未安装、未启用或未提供遥测接口）。"
        )


@pytest.mark.asyncio
async def test_missing_provider_does_not_import_its_implementation(
    kernel_factory, run_command, monkeypatch
):
    original_import = builtins.__import__

    def reject_observe(name, *args, **kwargs):
        if name.startswith("plugins.observe"):
            raise AssertionError("optional provider imported at runtime")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", reject_observe)
    async with kernel_factory() as (kernel, bus):
        assert "KVCache 不可用" in await run_command(kernel, bus, "/kvcache")


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
        reply = await run_command(kernel, bus, "/KVCACHE@MyBot 1")
        assert "⚡ KVCache · 最近 1 轮" in reply
        assert "Token  800 / 1,000" in reply
        assert "80.0%" in reply and "真实回复" in reply
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
