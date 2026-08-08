from __future__ import annotations

from agent.config_models import ModelRegistration
from core.roles.model_runtime import RoleModelRuntime
from core.roles.store import RoleStore


def registration(identifier: str, model: str) -> ModelRegistration:
    return ModelRegistration(
        id=identifier,
        provider="openai",
        base_url="https://example.com/v1",
        api_key="secret",
        model=model,
        effort="none",
    )


def test_runtime_resolves_dialogue_and_visual_fallback(tmp_path) -> None:
    dialogue = registration("00000000-0000-4000-a000-000000000001", "chat-model")
    visual = registration("00000000-0000-4000-a000-000000000002", "vision-model")
    store = RoleStore(tmp_path, default_dialogue_registration_id=dialogue.id)
    store.create_role(name="Mira", system_prompt="mira", role_id="mira")
    runtime = RoleModelRuntime(
        role_store=store,
        registrations=[dialogue, visual],
        system_prompt="system",
    )

    assert runtime.resolve("mira", "chat").model == "chat-model"
    assert runtime.resolve("mira", "vision").model == "chat-model"

    role = store.get_role("mira")
    assert role is not None
    store.update_role(
        "mira",
        runtime_config={
            **role.runtime_config,
            "visual_model_registration_id": visual.id,
        },
    )
    assert runtime.resolve("mira", "vision").model == "vision-model"


def test_runtime_snapshot_stays_stable_after_role_selection_changes(tmp_path) -> None:
    first = registration("00000000-0000-4000-a000-000000000001", "first-model")
    second = registration("00000000-0000-4000-a000-000000000002", "second-model")
    store = RoleStore(tmp_path, default_dialogue_registration_id=first.id)
    store.create_role(name="Mira", system_prompt="mira", role_id="mira")
    runtime = RoleModelRuntime(
        role_store=store,
        registrations=[first, second],
        system_prompt="system",
    )

    in_flight = runtime.resolve("mira", "chat")
    role = store.get_role("mira")
    assert role is not None
    store.update_role(
        "mira",
        runtime_config={
            **role.runtime_config,
            "dialogue_model_registration_id": second.id,
        },
    )

    assert in_flight.model == "first-model"
    assert runtime.resolve("mira", "chat").model == "second-model"
