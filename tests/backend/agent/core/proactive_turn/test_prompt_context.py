from types import SimpleNamespace

import pytest

from agent.core.proactive_turn.prompt_context import (
    build_runtime_context_message,
    build_system_prompt,
)
from proactive_v2.config import ProactiveConfig
from proactive_v2.context import AgentTickContext
from proactive_v2.gateway import GatewayResult


def test_proactive_system_prompt_rejects_missing_role_identity() -> None:
    with pytest.raises(ValueError, match="role.system_prompt required"):
        build_system_prompt("  ")


RECENT_CONTEXT = (
    "## 还在继续的事\n- 周末的旅行计划\n\n" "## 最近的对话\n- user: 群里的原话\n"
)


def test_proactive_context_leaves_out_the_raw_recent_turns() -> None:
    memory = SimpleNamespace(
        bind_session_metadata=lambda metadata: None,
        read_self=lambda: "",
        read_long_term=lambda: "",
        read_recent_context=lambda: RECENT_CONTEXT,
    )

    frame = build_runtime_context_message(
        cfg=ProactiveConfig(),
        session_key="role:mira",
        tool_deps=SimpleNamespace(memory=memory),
        workspace_context_fn=None,
        ctx=AgentTickContext(session_key="role:mira"),
        gateway_result=GatewayResult(),
    )

    # The raw turns span every thread; proactive reads the user context instead.
    assert "周末的旅行计划" in frame["content"]
    assert "群里的原话" not in frame["content"]
