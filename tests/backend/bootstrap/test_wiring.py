from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from agent.config import Config
from agent.config_models import Config as ConfigModel
from agent.config_models import WiringConfig
from agent.lifecycle.facade import TurnLifecycle
from shiori_sdk.core.conversation import StepFinished
from agent.looping.interrupt import TurnInterruptState
from agent.tools.message_push import MessagePushTool
from agent.tools.registry import ToolRegistry
from bootstrap.tools import (
    _build_loop_deps,
    _resolve_plugin_llm_dependencies,
    build_registered_tools,
)
from bootstrap.wiring import (
    resolve_context_factory,
    resolve_memory_toolset_provider,
    resolve_toolset_provider,
    wire_turn_lifecycle,
)
from bus.event_bus import EventBus
from core.roles import RoleStore
from tests.support.push import allow_every_role_target


def _toml_value(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    return str(value)


def _dump_toml(data: dict, prefix: tuple[str, ...] = ()) -> list[str]:
    lines: list[str] = []
    scalar_lines: list[str] = []

    for key, value in data.items():
        if isinstance(value, dict):
            continue
        if (
            isinstance(value, list)
            and value
            and all(isinstance(item, dict) for item in value)
        ):
            continue
        scalar_lines.append(f"{key} = {_toml_value(value)}")

    if prefix:
        lines.append(f"[{'.'.join(prefix)}]")
    lines.extend(scalar_lines)
    if scalar_lines:
        lines.append("")

    for key, value in data.items():
        if isinstance(value, dict):
            lines.extend(_dump_toml(value, prefix + (key,)))
        elif (
            isinstance(value, list)
            and value
            and all(isinstance(item, dict) for item in value)
        ):
            for item in value:
                lines.append(f"[[{'.'.join(prefix + (key,))}]]")
                for item_key, item_value in item.items():
                    lines.append(f"{item_key} = {_toml_value(item_value)}")
                lines.append("")
    return lines


def _write_toml(path: Path, payload: dict) -> None:
    path.write_text("\n".join(_dump_toml(payload)).strip() + "\n", encoding="utf-8")


def test_plugin_llm_dependencies_fall_back_to_main_model() -> None:
    config = ConfigModel(
        provider="openai",
        model="main-model",
        api_key="key",
    )
    provider = object()

    resolved_provider, resolved_model = _resolve_plugin_llm_dependencies(
        config,
        cast(Any, provider),
        None,
    )

    assert resolved_provider is provider
    assert resolved_model == "main-model"


def test_config_load_reads_wiring_block(tmp_path: Path):
    cfg_path = tmp_path / "config.toml"
    _write_toml(
        cfg_path,
        {
            "llm": {
                "registrations": [
                    {
                        "id": "00000000-0000-4000-a000-000000000001",
                        "provider": "openai",
                        "model": "m",
                        "api_key": "k",
                        "effort": "none",
                    }
                ],
            },
            "agent": {
                "system_prompt": "s",
                "wiring": {
                    "context": "default",
                    "memory": "default",
                    "memory_engine": "default",
                    "toolsets": ["schedule", "mcp"],
                },
            },
        },
    )

    cfg = Config.load(cfg_path)

    assert cfg.wiring.context == "default"
    assert cfg.wiring.memory == "default"
    assert cfg.wiring.toolsets == ["schedule", "mcp"]


def test_config_load_defaults_empty_toolsets_to_full_wiring(tmp_path: Path):
    cfg_path = tmp_path / "config.toml"
    _write_toml(
        cfg_path,
        {
            "llm": {
                "registrations": [
                    {
                        "id": "00000000-0000-4000-a000-000000000001",
                        "provider": "openai",
                        "model": "m",
                        "api_key": "k",
                        "effort": "none",
                    }
                ],
            },
            "agent": {
                "system_prompt": "s",
                "wiring": {
                    "toolsets": [],
                },
            },
        },
    )

    cfg = Config.load(cfg_path)

    assert cfg.wiring.toolsets == ["meta_common", "spawn", "schedule", "mcp"]


def test_config_load_migrates_legacy_memory_table(tmp_path: Path, caplog):
    cfg_path = tmp_path / "config.toml"
    _write_toml(
        cfg_path,
        {
            "llm": {
                "registrations": [
                    {
                        "id": "00000000-0000-4000-a000-000000000001",
                        "provider": "openai",
                        "model": "m",
                        "api_key": "k",
                        "effort": "none",
                    }
                ],
            },
            "agent": {"system_prompt": "s"},
            "memory": {
                "enabled": True,
                "engine": "memu",
                "embedding": {
                    "model": "legacy-embedding",
                    "api_key": "legacy-key",
                    "output_dimensionality": 1536,
                },
                "retrieval": {"score_threshold": 0.99},
            },
        },
    )

    with caplog.at_level("WARNING"):
        cfg = Config.load(cfg_path)

    assert not hasattr(cfg, "memory")
    plugin = cfg.plugins["default_memory"]
    assert plugin["enabled"] is True
    assert plugin["embedding_model"] == "legacy-embedding"
    assert plugin["embedding_api_key"] == "legacy-key"
    assert plugin["embedding_base_url"] == ""
    assert plugin["output_dimensionality"] == 1536
    assert "score_threshold" not in plugin
    import tomllib

    assert "memory" not in tomllib.loads(cfg_path.read_text(encoding="utf-8"))
    assert any("memu" in record.message for record in caplog.records)


def test_config_load_ignores_wiring_memory_engine(tmp_path: Path):
    cfg_path = tmp_path / "config.toml"
    _write_toml(
        cfg_path,
        {
            "llm": {
                "registrations": [
                    {
                        "id": "00000000-0000-4000-a000-000000000001",
                        "provider": "openai",
                        "model": "m",
                        "api_key": "k",
                        "effort": "none",
                    }
                ],
            },
            "agent": {
                "system_prompt": "s",
                "wiring": {
                    "memory_engine": "memu",
                },
            },
            "memory": {
                "enabled": True,
            },
        },
    )

    cfg = Config.load(cfg_path)

    assert cfg.wiring.memory == "default"
    assert not hasattr(cfg, "memory")


def test_config_load_ignores_legacy_memory_v2_enabled(tmp_path: Path):
    cfg_path = tmp_path / "config.toml"
    _write_toml(
        cfg_path,
        {
            "llm": {
                "registrations": [
                    {
                        "id": "00000000-0000-4000-a000-000000000001",
                        "provider": "openai",
                        "model": "m",
                        "api_key": "k",
                        "effort": "none",
                    }
                ],
            },
            "agent": {"system_prompt": "s"},
            "memory_v2": {
                "enabled": True,
            },
        },
    )

    original = cfg_path.read_text(encoding="utf-8")

    cfg = Config.load(cfg_path)

    assert not hasattr(cfg, "memory_v2")
    assert not hasattr(cfg, "memory")
    assert "default_memory" not in cfg.plugins
    assert cfg_path.read_text(encoding="utf-8") == original


def test_config_load_rejects_legacy_socket_configuration(tmp_path: Path):
    cfg_path = tmp_path / "config.toml"
    _write_toml(
        cfg_path,
        {
            "llm": {
                "registrations": [
                    {
                        "id": "00000000-0000-4000-a000-000000000001",
                        "provider": "openai",
                        "model": "m",
                        "api_key": "k",
                        "effort": "none",
                    }
                ],
            },
            "agent": {
                "system_prompt": "s",
                "context": {
                    "memory_window": 20,
                },
            },
            "channels": {
                "socket": "/tmp/dev-shiori.sock",
            },
        },
    )

    with pytest.raises(ValueError, match=r"\[channels.socket\]"):
        _ = Config.load(cfg_path)


def test_config_load_reads_agent_dev_mode(tmp_path: Path):
    cfg_path = tmp_path / "config.toml"
    _write_toml(
        cfg_path,
        {
            "llm": {
                "registrations": [
                    {
                        "id": "00000000-0000-4000-a000-000000000001",
                        "provider": "openai",
                        "model": "m",
                        "api_key": "k",
                        "effort": "none",
                    }
                ],
            },
            "agent": {
                "system_prompt": "s",
                "dev_mode": True,
            },
        },
    )

    cfg = Config.load(cfg_path)

    assert cfg.dev_mode is True


def test_config_load_accepts_dev_model_alias(tmp_path: Path):
    cfg_path = tmp_path / "config.toml"
    _write_toml(
        cfg_path,
        {
            "llm": {
                "registrations": [
                    {
                        "id": "00000000-0000-4000-a000-000000000001",
                        "provider": "openai",
                        "model": "m",
                        "api_key": "k",
                        "effort": "none",
                    }
                ],
            },
            "agent": {
                "system_prompt": "s",
                "dev_model": True,
            },
        },
    )

    cfg = Config.load(cfg_path)

    assert cfg.dev_mode is True


def test_config_load_rejects_removed_qqbot_channel_block(
    tmp_path: Path,
):
    cfg_path = tmp_path / "config.toml"
    _write_toml(
        cfg_path,
        {
            "llm": {
                "registrations": [
                    {
                        "id": "00000000-0000-4000-a000-000000000001",
                        "provider": "openai",
                        "model": "m",
                        "api_key": "k",
                        "effort": "none",
                    }
                ],
            },
            "agent": {
                "system_prompt": "s",
            },
            "channels": {
                "qqbot": {
                    "app_id": "app",
                    "client_secret": "${QQBOT_SECRET}",
                    "allow_from": ["user-openid"],
                    "groups": [
                        {
                            "group_openid": "group-openid",
                            "allow_from": ["member-openid"],
                            "require_at": True,
                            "allow_proactive": True,
                        }
                    ],
                },
            },
        },
    )

    with pytest.raises(ValueError, match=r"\[channels.qqbot\]"):
        _ = Config.load(cfg_path)


def test_config_load_rejects_removed_fitbit_integration_block(tmp_path: Path):
    cfg_path = tmp_path / "config.toml"
    _write_toml(
        cfg_path,
        {
            "llm": {
                "registrations": [
                    {
                        "id": "00000000-0000-4000-a000-000000000001",
                        "provider": "openai",
                        "model": "m",
                        "api_key": "k",
                        "effort": "none",
                    }
                ],
            },
            "agent": {
                "system_prompt": "s",
            },
            "integrations": {
                "fitbit": {
                    "enabled": True,
                }
            },
        },
    )

    with pytest.raises(ValueError, match=r"\[integrations.fitbit\]"):
        _ = Config.load(cfg_path)


def test_config_load_rejects_removed_socket_configuration(
    tmp_path: Path,
):
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(
        """
[[llm.registrations]]
id = "00000000-0000-4000-a000-000000000001"
provider = "openai"
model = "m"
api_key = "k"
effort = "none"

[agent]
system_prompt = "s"
max_tokens = 256

[agent.context]
memory_window = 12

[channels]
socket = "/tmp/toml-shiori.sock"

[integrations.fitbit]
enabled = true
""".strip() + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"\[channels.socket\]"):
        _ = Config.load(cfg_path)


@pytest.mark.parametrize(
    ("channel", "values"),
    [
        ("qq", {"bot_uin": "10001", "websocket_open_timeout_seconds": 9.5}),
        ("telegram", {"token": "123:abc"}),
    ],
)
def test_config_load_rejects_removed_channel_blocks(
    tmp_path: Path, channel: str, values: dict[str, object]
):
    cfg_path = tmp_path / "config.toml"
    _write_toml(
        cfg_path,
        {
            "llm": {
                "registrations": [
                    {
                        "id": "00000000-0000-4000-a000-000000000001",
                        "provider": "openai",
                        "model": "m",
                        "api_key": "k",
                        "effort": "none",
                    }
                ],
            },
            "agent": {
                "system_prompt": "s",
            },
            "channels": {channel: values},
        },
    )

    with pytest.raises(ValueError, match=rf"配置项已移除: \[channels\.{channel}\]"):
        Config.load(cfg_path)


def test_build_registered_tools_respects_toolset_order_and_subset(
    monkeypatch, tmp_path: Path
):
    calls: list[str] = []

    class _MemoryProvider:
        def register(self, registry, deps):
            calls.append("memory")
            runtime = SimpleNamespace()
            return SimpleNamespace(extras={"memory_runtime": runtime})

    class _ToolsetProvider:
        def __init__(self, name: str) -> None:
            self._name = name

        def register(self, registry, deps):
            calls.append(self._name)
            extras = (
                {"mcp_registry": SimpleNamespace(shutdown=AsyncMock())}
                if self._name == "mcp"
                else {}
            )
            return SimpleNamespace(extras=extras)

    monkeypatch.setattr(
        "bootstrap.tools.resolve_memory_toolset_provider",
        lambda name: _MemoryProvider(),
    )
    monkeypatch.setattr(
        "bootstrap.tools.resolve_toolset_provider",
        lambda name, readonly_tools=None: _ToolsetProvider(name),
    )
    monkeypatch.setattr("bootstrap.tools.build_readonly_tools", lambda *_, **__: {})
    monkeypatch.setattr(
        "bootstrap.tools.build_scheduler",
        lambda *_args, **_kwargs: SimpleNamespace(),
    )
    config = ConfigModel(
        provider="openai",
        model="m",
        api_key="k",
        wiring=WiringConfig(toolsets=["schedule", "mcp"]),
    )
    build_registered_tools(
        config=config,
        workspace=tmp_path,
        http_resources=cast(Any, SimpleNamespace()),
        bus=cast(Any, SimpleNamespace()),
        provider=object(),
        light_provider=object(),
        session_store=object(),
        tools=ToolRegistry(),
        event_publisher=EventBus(),
        agent_loop_provider=lambda: None,
        push_tool=MessagePushTool(role_target_validator=allow_every_role_target),
    )

    assert calls == ["memory", "schedule", "mcp"]


def test_build_loop_deps_uses_context_factory(monkeypatch, tmp_path: Path):
    observed: dict[str, object] = {}
    fake_context = object()
    markdown_store = object()
    markdown_maintenance = SimpleNamespace(
        bind_lifecycle=lambda request: None,
        listening_trigger=SimpleNamespace(attach=lambda store: None),
    )

    monkeypatch.setattr(
        "bootstrap.tools.resolve_context_factory",
        lambda name: (
            lambda workspace, memory_store, roles: observed.update(
                {
                    "name": name,
                    "workspace": workspace,
                    "memory_store": memory_store,
                    "roles": roles,
                }
            )
            or fake_context
        ),
    )

    config = ConfigModel(
        provider="openai",
        model="m",
        api_key="k",
        wiring=WiringConfig(context="default"),
    )
    roles = RoleStore(tmp_path)
    deps = _build_loop_deps(
        config=config,
        workspace=tmp_path,
        runtime_roles=roles,
        group_environment=cast(
            Any, SimpleNamespace(conversation_store=SimpleNamespace(listening=None))
        ),
        bus=cast(Any, SimpleNamespace()),
        provider=cast(Any, object()),
        light_provider=None,
        tools=ToolRegistry(),
        session_manager=cast(
            Any,
            SimpleNamespace(
                get_or_create=lambda key: None,
                commit_consolidation=lambda request, write_memory, publish_committed: None,
                retry_memory_consumers=lambda key, consumer: None,
                record_memory_publication=lambda key, payload: None,
                record_recent_context=lambda key, ids, ownership: None,
            ),
        ),
        presence=cast(Any, None),
        processing_state=cast(Any, SimpleNamespace()),
        event_bus=EventBus(),
        memory_runtime=cast(
            Any,
            SimpleNamespace(
                current_engine=object,
                markdown=SimpleNamespace(
                    store=markdown_store,
                    maintenance=markdown_maintenance,
                ),
            ),
        ),
        relationship_runtime=cast(Any, SimpleNamespace()),
    )

    assert observed["name"] == "default"
    assert observed["workspace"] == tmp_path
    assert observed["memory_store"] is markdown_store
    assert observed["roles"] is roles
    assert deps.context is fake_context


def test_wiring_error_messages_list_available_choices():
    try:
        resolve_context_factory("bad")
    except ValueError as exc:
        assert "可选值" in str(exc)
        assert "default" in str(exc)
    else:
        raise AssertionError("resolve_context_factory should fail for bad name")

    try:
        resolve_memory_toolset_provider("bad")
    except ValueError as exc:
        assert "可选值" in str(exc)
        assert "default" in str(exc)
    else:
        raise AssertionError("resolve_memory_toolset_provider should fail for bad name")

    try:
        resolve_toolset_provider("bad")
    except ValueError as exc:
        assert "可选值" in str(exc)
        assert "meta_common" in str(exc)
    else:
        raise AssertionError("resolve_toolset_provider should fail for bad name")


@pytest.mark.asyncio
async def test_wire_turn_lifecycle_registers_step_finished_progress_handler():
    bus = EventBus()
    states: dict[str, TurnInterruptState] = {
        "telegram:1": TurnInterruptState(
            session_key="telegram:1",
            original_user_message="hello",
        )
    }
    wire_turn_lifecycle(
        lifecycle=TurnLifecycle(bus),
        active_turn_states=states,
    )

    await bus.emit(
        StepFinished(
            session_key="telegram:1",
            channel="telegram",
            chat_id="1",
            iteration=0,
            context_tokens_estimate=0,
            input_limit_tokens=None,
            tools_called=("noop",),
            partial_reply="部分回复",
            tools_used_so_far=("a", "b"),
            tool_chain_partial=({"text": "tool", "calls": []},),
            partial_thinking="思考",
            has_more=True,
        )
    )

    state = states["telegram:1"]
    assert state.partial_reply == "部分回复"
    assert state.partial_thinking == "思考"
    assert state.tools_used == ["a", "b"]
    assert state.tool_chain_partial == [{"text": "tool", "calls": []}]


async def test_buffered_progress_retains_tools_without_claiming_unsent_dialogue():
    from agent.turns.reply_sequence import buffered_reply_scope

    bus = EventBus()
    state = TurnInterruptState("role:a", "hello")
    wire_turn_lifecycle(TurnLifecycle(bus), active_turn_states={"role:a": state})
    with buffered_reply_scope(True):
        await bus.emit(
            StepFinished(
                session_key="role:a",
                channel="desktop",
                chat_id="role:a",
                iteration=0,
                context_tokens_estimate=0,
                input_limit_tokens=None,
                tools_called=("lookup",),
                partial_reply="未发送\n<message-break/>\n尾部",
                tools_used_so_far=("lookup",),
                tool_chain_partial=(
                    {"text": "未发送铺垫", "calls": [{"name": "lookup"}]},
                ),
                partial_thinking="thinking",
                has_more=False,
            )
        )
    assert state.partial_reply == ""
    assert state.partial_thinking == "thinking"
    assert state.tools_used == ["lookup"]
    assert state.tool_chain_partial == [{"text": "", "calls": [{"name": "lookup"}]}]


def test_build_registered_tools_without_mcp_toolset_still_returns_empty_registry(
    monkeypatch, tmp_path: Path
):
    monkeypatch.setattr(
        "bootstrap.tools.resolve_memory_toolset_provider",
        lambda name: SimpleNamespace(
            register=lambda registry, deps: SimpleNamespace(
                extras={"memory_runtime": SimpleNamespace()}
            )
        ),
    )
    monkeypatch.setattr(
        "bootstrap.tools.resolve_toolset_provider",
        lambda name, readonly_tools=None: SimpleNamespace(
            register=lambda registry, deps: SimpleNamespace(extras={})
        ),
    )
    monkeypatch.setattr("bootstrap.tools.build_readonly_tools", lambda *_, **__: {})
    monkeypatch.setattr(
        "bootstrap.tools.build_scheduler",
        lambda *_args, **_kwargs: SimpleNamespace(),
    )
    config = ConfigModel(
        provider="openai",
        model="m",
        api_key="k",
        wiring=WiringConfig(toolsets=["schedule"]),
    )
    _, _, mcp_registry, _ = build_registered_tools(
        config=config,
        workspace=tmp_path,
        http_resources=cast(Any, SimpleNamespace()),
        bus=cast(Any, SimpleNamespace()),
        provider=object(),
        light_provider=object(),
        session_store=object(),
        tools=ToolRegistry(),
        event_publisher=EventBus(),
        agent_loop_provider=lambda: None,
        push_tool=MessagePushTool(role_target_validator=allow_every_role_target),
    )

    assert mcp_registry is not None
    assert mcp_registry.list_servers() == "当前没有已注册的 MCP server。"


def test_wiring_imports_without_preloading_the_plugin_kernel():
    result = subprocess.run(
        [sys.executable, "-c", "import bootstrap.wiring"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
