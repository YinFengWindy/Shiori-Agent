from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core.roles.relationship_runtime.snapshot import RelationshipSnapshotOptimizer


@pytest.mark.asyncio
async def test_optimizer_uses_the_role_dialogue_model_snapshot() -> None:
    selected_provider = SimpleNamespace(
        chat=AsyncMock(return_value=SimpleNamespace(content="{}"))
    )
    fallback_provider = SimpleNamespace(
        chat=AsyncMock(side_effect=AssertionError("fallback"))
    )
    activations: list[tuple[str, str]] = []

    class _WorldRegistry:
        async def get(self, role_id: str):
            self.role_id = role_id
            return self

        @contextmanager
        def activate_model(self, purpose: str):
            activations.append((self.role_id, purpose))
            yield SimpleNamespace(provider=selected_provider, model="role-model")

    class _RelationshipRuntime:
        async def generate_snapshot_via_llm(self, _role_id: str, **kwargs):
            await kwargs["provider"].chat(
                messages=[],
                tools=[],
                model=kwargs["model"],
                max_tokens=kwargs["max_tokens"],
            )
            return {"role_id": "mira"}

        def recompute_loneliness(self, _role_id: str, *, now) -> None:
            return None

        def mark_snapshot_error(self, _role_id: str, **_kwargs) -> None:
            raise AssertionError("snapshot should not fail")

    optimizer = RelationshipSnapshotOptimizer(
        _RelationshipRuntime(),
        provider=fallback_provider,
        model="base-model",
        world_registry=_WorldRegistry(),
    )

    result = await optimizer.optimize(role_id="mira")

    assert result == {"role_id": "mira"}
    assert activations == [("mira", "chat")]
    assert selected_provider.chat.await_args.kwargs["model"] == "role-model"
    fallback_provider.chat.assert_not_called()
