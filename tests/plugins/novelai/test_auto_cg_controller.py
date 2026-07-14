from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from agent.lifecycle.types import BeforeTurnCtx
from agent.lifecycle.types import AfterTurnCtx
from agent.plugins.context import PluginKVStore
from agent.tools.message_push import MessagePushTool
from agent.tools.registry import ToolRegistry
from core.integrations.novelai.models import NovelAISettings
from plugins.novelai.auto_cg import AutoCgPolicy
from plugins.novelai.auto_cg_controller import AutoCgController
from plugins.novelai.scene_decision import SceneCgDecision, SceneCgDecisionInput


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


@pytest.mark.asyncio
async def test_controller_records_cooldown_only_after_all_media_pushes_succeed(
    tmp_path: Path,
) -> None:
    policy = AutoCgPolicy(PluginKVStore(tmp_path / ".kv.json"))
    push_tool = MessagePushTool()

    async def failing_image_sender(_chat_id: str, _image: str) -> None:
        raise RuntimeError("desktop unavailable")

    push_tool.register_channel("desktop", image=failing_image_sender)
    registry = ToolRegistry()
    registry.register(push_tool)

    async def decide(*_args: Any, **_kwargs: Any) -> SceneCgDecision:
        return SceneCgDecision(
            should_generate=True,
            scene_key="rain",
            prompt="a rainy street",
        )

    class GenerateTool:
        async def execute(self, **_kwargs: Any) -> str:
            return '{"output_paths": ["cg.png"]}'

    controller = AutoCgController(
        settings=NovelAISettings(enabled=True, token="novel-token"),
        role_store=cast(Any, None),
        policy=policy,
        light_provider=cast(Any, object()),
        light_model="light-model",
        session_manager=cast(
            Any,
            SimpleNamespace(
                get_or_create=lambda _session_key: SimpleNamespace(
                    metadata={"role_id": "mira"}
                )
            ),
        ),
        generate_tool=cast(Any, GenerateTool()),
        tool_registry=registry,
        decision_provider=decide,
    )
    ctx = AfterTurnCtx(
        session_key="role:mira",
        channel="desktop",
        chat_id="role:mira",
        reply="继续下雨了。",
        tools_used=(),
        thinking=None,
        will_dispatch=True,
    )
    decision_input = SceneCgDecisionInput(
        role_name="Mira",
        role_prompt="prompt",
        user_message="下雨了吗？",
    )

    with pytest.raises(RuntimeError, match="自动场景 CG 补发失败"):
        await controller._run(ctx, decision_input)

    assert policy.cooldown_remaining("role:mira") == 0
