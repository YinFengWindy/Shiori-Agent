from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core.roles.self_seed import LlmRoleSelfSeedGenerator


@pytest.mark.asyncio
async def test_self_seed_uses_the_role_dialogue_model_snapshot() -> None:
    selected_provider = SimpleNamespace(
        chat=AsyncMock(return_value=SimpleNamespace(content="# 角色自我认知"))
    )
    fallback_provider = SimpleNamespace(
        chat=AsyncMock(side_effect=AssertionError("fallback"))
    )
    activations: list[tuple[str, str]] = []

    class _ModelRuntime:
        @contextmanager
        def activate(self, role_id: str, purpose: str):
            activations.append((role_id, purpose))
            yield SimpleNamespace(provider=selected_provider, model="role-model")

    generator = LlmRoleSelfSeedGenerator(
        provider=fallback_provider,
        model="base-model",
        model_runtime=_ModelRuntime(),
    )
    role = SimpleNamespace(
        id="mira",
        name="Mira",
        description="陪伴者",
        background="相识不久",
        system_prompt="用中文回复",
    )

    result = await generator.agenerate(role)

    assert result == "# 角色自我认知"
    assert activations == [("mira", "chat")]
    assert selected_provider.chat.await_args.kwargs["model"] == "role-model"
    fallback_provider.chat.assert_not_called()
