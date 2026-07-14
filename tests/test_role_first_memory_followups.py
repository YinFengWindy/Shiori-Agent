from __future__ import annotations

from pathlib import Path

import pytest

from prompts.background import (
    build_general_subagent_prompt,
    build_research_subagent_prompt,
)
from proactive_v2.agent_tick_factory import AgentTickDeps, AgentTickFactory
from proactive_v2.config_loader import load_proactive_config
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


def test_load_proactive_config_allows_role_target_to_be_owned_by_role_runtime() -> None:
    config = load_proactive_config(
        {
            "enabled": True,
            "profile": "daily",
            "target": {
                "channel": "telegram",
                "chat_id": "1",
                "role_id": "",
            },
        }
    )

    assert config.default_role_id == ""


def test_agent_tick_factory_requires_default_role_id() -> None:
    deps = AgentTickDeps(
        cfg=type(
            "Cfg",
            (),
            {
                "default_role_id": "",
                "default_chat_id": "cid",
                "agent_tick_model": "",
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
        presence=type("Presence", (), {"get_last_user_at": staticmethod(lambda _: None)})(),
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
        pool=McpClientPool(),
    )

    with pytest.raises(RuntimeError, match="default_role_id required for proactive session key"):
        AgentTickFactory(deps).build()
