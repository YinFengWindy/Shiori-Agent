from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core.roles.self_seed import LlmRoleSelfSeedGenerator
from core.roles import RoleStore
from core.roles.model_runtime import RoleModelSnapshot


@pytest.mark.asyncio
async def test_self_seed_uses_the_role_dialogue_model_snapshot(tmp_path) -> None:
    selected_provider = SimpleNamespace(
        chat=AsyncMock(return_value=SimpleNamespace(content="# 角色自我认知"))
    )
    generator = LlmRoleSelfSeedGenerator()
    role = RoleStore(tmp_path).create_role(
        role_id="mira",
        name="Mira",
        description="陪伴者",
        background="相识不久",
        system_prompt="用中文回复",
    )

    result = await generator.agenerate(
        role,
        RoleModelSnapshot(
            "selected",
            selected_provider,
            "role-model",
            "none",
            role_id=role.id,
        ),
    )

    assert result == "# 角色自我认知"
    assert selected_provider.chat.await_args.kwargs["model"] == "role-model"
    assert selected_provider.chat.await_args.kwargs["max_tokens"] is None


@pytest.mark.asyncio
async def test_self_seed_allows_generation_past_one_minute(tmp_path, monkeypatch):
    loop = asyncio.get_running_loop()
    real_time = loop.time
    elapsed = 0.0
    monkeypatch.setattr(loop, "time", lambda: real_time() + elapsed)
    started = asyncio.Event()
    release = asyncio.Event()

    async def generate(**kwargs):
        started.set()
        await release.wait()
        return SimpleNamespace(content="# 我是谁\n\n完整的角色自述")

    provider = SimpleNamespace(chat=AsyncMock(side_effect=generate))
    role = RoleStore(tmp_path).create_role(name="Mira", system_prompt="详细设定" * 5000)
    snapshot = RoleModelSnapshot("selected", provider, "test", "none", role_id=role.id)
    task = asyncio.create_task(LlmRoleSelfSeedGenerator().agenerate(role, snapshot))
    try:
        await started.wait()
        # Advance the event-loop clock without waiting a real minute; any due
        # timeout gets a chance to run while the model is still generating.
        elapsed = 61.0
        for _ in range(5):
            await asyncio.sleep(0)
        release.set()
        assert await task == "# 我是谁\n\n完整的角色自述"
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_self_seed_compiles_stable_profile_without_transient_knowledge(
    tmp_path,
) -> None:
    provider = SimpleNamespace(
        chat=AsyncMock(return_value=SimpleNamespace(content="# 我是谁"))
    )
    role = RoleStore(tmp_path).create_role(
        role_id="mira",
        name="Mira",
        system_prompt="旧提示词",
        background="旧背景",
        runtime_config={"mood_catalog": ["平静"]},
        profile={
            "character": {
                "profile": "{{char}}是{{user}}的向导",
                "personality": "温柔",
                "behavior_rules": "诚实",
                "response_constraints": "简洁",
                "nickname": "小栞",
            },
            "knowledge_base": {
                "enabled": True,
                "entries": [{"content": "当前聊天知识", "always_active": True}],
            },
        },
    )

    await LlmRoleSelfSeedGenerator().agenerate(
        role,
        RoleModelSnapshot(
            "selected",
            provider,
            "test",
            "none",
            role_id=role.id,
        ),
    )

    prompt = provider.chat.await_args.kwargs["messages"][1]["content"]
    assert "小栞是用户的向导" in prompt
    assert "温柔" in prompt and "诚实" in prompt and "简洁" in prompt
    assert "旧提示词" not in prompt and "旧背景" not in prompt
    assert "当前聊天知识" not in prompt and "Mood Output Contract" not in prompt


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response", ["", "   ", RuntimeError("provider unavailable"), TimeoutError()]
)
async def test_self_seed_propagates_failures_and_rejects_empty_content(
    tmp_path, response
):
    provider = SimpleNamespace(
        chat=AsyncMock(
            side_effect=response if isinstance(response, Exception) else None,
            return_value=SimpleNamespace(content=response),
        )
    )
    role = RoleStore(tmp_path).create_role(name="Mira", system_prompt="mira")
    with pytest.raises(
        type(response) if isinstance(response, Exception) else ValueError
    ):
        await LlmRoleSelfSeedGenerator().agenerate(
            role,
            RoleModelSnapshot(
                "selected",
                provider,
                "test",
                "none",
                role_id=role.id,
            ),
        )
