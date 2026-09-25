from __future__ import annotations

from pathlib import Path

import pytest

from prompts.background import (
    build_general_subagent_prompt,
    build_research_subagent_prompt,
)
from proactive_v2.agent_tick_factory import AgentTickDeps, AgentTickFactory
from proactive_v2.config_loader import ProactiveConfigError, load_proactive_config
from proactive_v2.mcp_sources import McpClientPool


def test_background_prompts_reference_role_memory(tmp_path: Path) -> None:
    text = build_research_subagent_prompt(tmp_path, tmp_path / "task")
    assert "roles/<role_id>/memory/" in text
    assert "/memory/SELF.md" not in text
    assert "/memory/HISTORY.md" not in text

    text2 = build_general_subagent_prompt(tmp_path, tmp_path / "task")
    assert "roles/<role_id>/memory/" in text2
    assert "/memory/SELF.md" not in text2
    assert "/memory/HISTORY.md" not in text2


def test_load_proactive_config_names_the_role_only_by_argument() -> None:
    assert load_proactive_config({"profile": "daily"}).role_id == ""
    assert load_proactive_config({"profile": "daily"}, role_id="mira").role_id == "mira"


@pytest.mark.parametrize(
    "legacy",
    [
        {"target": {"channel": "telegram", "chat_id": "1"}},
        {"default_channel": "telegram"},
        {"default_chat_id": "1"},
        {"default_role_id": "mira"},
    ],
)
def test_load_proactive_config_rejects_the_removed_global_target(legacy) -> None:
    with pytest.raises(ProactiveConfigError, match="配置项已移除"):
        load_proactive_config({"profile": "daily", **legacy})


def test_agent_tick_factory_requires_role_id() -> None:
    deps = AgentTickDeps(
        cfg=type(
            "Cfg",
            (),
            {
                "role_id": "",
                "agent_tick_web_fetch_max_chars": 4000,
                "message_dedupe_recent_n": 3,
            },
        )(),
        sense=type(
            "Sense",
            (),
            {
                "target_session_key": staticmethod(lambda: "telegram:1"),
                "target_transport": staticmethod(lambda: ("telegram", "1")),
                "collect_recent": staticmethod(lambda: []),
                "collect_recent_proactive": staticmethod(lambda n: []),
            },
        )(),
        presence=type(
            "Presence", (), {"get_last_user_at": staticmethod(lambda _: None)}
        )(),
        provider=type("Provider", (), {})(),
        model="m",
        max_tokens=128,
        memory=None,
        state_store=type("State", (), {})(),
        any_action_gate=type("Gate", (), {})(),
        passive_busy_fn=None,
        deduper=None,
        rng=type("Rng", (), {})(),
        workspace_context_fn=lambda: "",
        role_prompt_fn=lambda: "测试角色提示词",
        pool=McpClientPool(),
    )

    with pytest.raises(
        RuntimeError, match="role_id required for proactive session key"
    ):
        AgentTickFactory(deps).build()
