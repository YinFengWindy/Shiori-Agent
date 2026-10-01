from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

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

    class _RoleRuntimeRegistry:
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
        role_runtime_registry=_RoleRuntimeRegistry(),
    )

    result = await optimizer.optimize(role_id="mira")

    assert result == {"role_id": "mira"}
    assert activations == [("mira", "chat")]
    assert selected_provider.chat.await_args.kwargs["model"] == "role-model"
    fallback_provider.chat.assert_not_called()


@pytest.mark.asyncio
async def test_optimizer_records_and_propagates_provider_failure_without_lock_leak():
    error = RuntimeError("relationship provider unavailable")
    runtime = SimpleNamespace(
        generate_snapshot_via_llm=AsyncMock(side_effect=error),
        mark_snapshot_error=Mock(),
        recompute_loneliness=Mock(),
    )
    optimizer = RelationshipSnapshotOptimizer(
        runtime, provider=SimpleNamespace(), model="test"
    )
    with pytest.raises(RuntimeError) as failure:
        await optimizer.optimize(role_id="mira")
    assert failure.value is error
    assert not optimizer.is_running
    runtime.mark_snapshot_error.assert_called_once()
    assert runtime.mark_snapshot_error.call_args.args == ("mira",)
    assert runtime.mark_snapshot_error.call_args.kwargs["error"] == str(error)
    runtime.recompute_loneliness.assert_not_called()

    runtime.generate_snapshot_via_llm.side_effect = None
    runtime.generate_snapshot_via_llm.return_value = {"role_id": "mira"}
    assert await optimizer.optimize(role_id="mira") == {"role_id": "mira"}
    runtime.recompute_loneliness.assert_called_once()
