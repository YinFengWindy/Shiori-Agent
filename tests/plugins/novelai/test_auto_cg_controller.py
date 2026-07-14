from datetime import datetime
from pathlib import Path
from typing import Any, cast

from agent.lifecycle.types import BeforeTurnCtx
from agent.plugins.context import PluginKVStore
from core.integrations.novelai.models import NovelAISettings
from plugins.novelai.auto_cg import AutoCgPolicy
from plugins.novelai.auto_cg_controller import AutoCgController


def test_controller_advances_cooldown_while_decision_is_unavailable(
    tmp_path: Path,
) -> None:
    policy = AutoCgPolicy(PluginKVStore(tmp_path / ".kv.json"))
    session_key = "role:mira"
    policy.advance_turn(session_key)
    policy.record_success(session_key, "rain")
    controller = AutoCgController(
        settings=NovelAISettings(enabled=True, token="novel-token"),
        role_store=cast(Any, None),
        policy=policy,
        light_provider=None,
        light_model="",
        session_manager=None,
        generate_tool=cast(Any, None),
        tool_registry=cast(Any, None),
    )
    turn = BeforeTurnCtx(
        session_key=session_key,
        channel="desktop",
        chat_id="chat",
        content="message",
        timestamp=datetime.now(),
        retrieved_memory_block="",
        retrieval_trace_raw=None,
        history_messages=(),
    )

    for _ in range(9):
        controller.capture_turn(turn)

    assert policy.cooldown_remaining(session_key) == 0
