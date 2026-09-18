from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from agent.config_models import ModelRegistration
from agent.provider import LLMProvider
from core.roles.model_runtime import (
    ModelConfigurationError,
    RoleAwareProvider,
    RoleModelRuntime,
)
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


def test_empty_runtime_keeps_roles_browsable_and_reports_missing_capability(tmp_path):
    store = RoleStore(tmp_path)
    store.create_role(name="Mira", system_prompt="mira", role_id="mira")
    runtime = RoleModelRuntime(role_store=store, registrations=[])
    assert runtime.availability("mira")["reason"] == "no_models"
    with pytest.raises(ModelConfigurationError) as caught:
        runtime.resolve("mira", "chat")
    assert caught.value.to_details()["role_id"] == "mira"
    assert store.get_role("mira") is not None


@pytest.mark.parametrize(
    "binding,reason", [("", "role_unbound"), ("deleted", "registration_missing")]
)
def test_runtime_reports_unbound_and_dangling_model_choices(tmp_path, binding, reason):
    store = RoleStore(tmp_path)
    store.create_role(
        name="Mira",
        system_prompt="mira",
        role_id="mira",
        runtime_config={
            "dialogue_model_registration_id": binding,
        },
    )
    runtime = RoleModelRuntime(
        role_store=store, registrations=[registration("model", "chat")]
    )
    assert runtime.availability("mira")["reason"] == reason


def test_availability_does_not_construct_provider_and_reports_incomplete_fields(
    tmp_path,
):
    store = RoleStore(tmp_path)
    store.create_role(
        name="Mira",
        system_prompt="mira",
        role_id="mira",
        runtime_config={"dialogue_model_registration_id": "model"},
    )
    runtime = RoleModelRuntime(
        role_store=store,
        registrations=[
            replace(
                registration("model", "chat"),
                api_key="${MISSING_KEY}",
                model="",
            )
        ],
    )
    with patch(
        "core.roles.model_runtime.LLMProvider",
        side_effect=AssertionError("network client"),
    ):
        availability = runtime.availability("mira")
    assert availability["reason"] == "connection_incomplete"
    assert availability["fields"] == ["model", "api_key"]


def test_accepted_snapshot_is_retained_for_nested_activation(tmp_path):
    store = RoleStore(tmp_path)
    store.create_role(
        name="Mira",
        system_prompt="mira",
        role_id="mira",
        runtime_config={"dialogue_model_registration_id": "first"},
    )
    runtime = RoleModelRuntime(
        role_store=store, registrations=[registration("first", "chat")]
    )
    with runtime.activate("mira", "chat") as accepted:
        store.update_role("mira", runtime_config={"dialogue_model_registration_id": ""})
        with runtime.activate("mira", "chat") as nested:
            assert nested is accepted
    with pytest.raises(ModelConfigurationError):
        runtime.resolve("mira", "chat")


@pytest.mark.asyncio
async def test_generation_reuses_provider_and_releases_it_once_on_close(tmp_path):
    store = RoleStore(tmp_path)
    store.create_role(
        name="Mira",
        system_prompt="mira",
        role_id="mira",
        runtime_config={"dialogue_model_registration_id": "first"},
    )
    runtime = RoleModelRuntime(
        role_store=store, registrations=[registration("first", "chat")]
    )
    with patch("core.roles.model_runtime.LLMProvider") as provider_class:
        provider_class.return_value.aclose = AsyncMock()
        first = runtime.resolve("mira", "chat")
        second = runtime.resolve("mira", "chat")
        assert first.provider is second.provider
        provider_class.assert_called_once()
        await runtime.aclose()
        await runtime.aclose()
        first.provider.aclose.assert_awaited_once()


def test_runtime_resolves_dialogue_and_visual_fallback(tmp_path) -> None:
    dialogue = registration("00000000-0000-4000-a000-000000000001", "chat-model")
    visual = registration("00000000-0000-4000-a000-000000000002", "vision-model")
    store = RoleStore(tmp_path)
    store.create_role(
        name="Mira",
        system_prompt="mira",
        role_id="mira",
        runtime_config={"dialogue_model_registration_id": dialogue.id},
    )
    runtime = RoleModelRuntime(
        role_store=store,
        registrations=[dialogue, visual],
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
    store = RoleStore(tmp_path)
    store.create_role(
        name="Mira",
        system_prompt="mira",
        role_id="mira",
        runtime_config={"dialogue_model_registration_id": first.id},
    )
    runtime = RoleModelRuntime(
        role_store=store,
        registrations=[first, second],
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


def test_runtime_uses_role_dialogue_effort_override(tmp_path) -> None:
    dialogue = registration("00000000-0000-4000-a000-000000000001", "chat-model")
    visual = ModelRegistration(
        id="00000000-0000-4000-a000-000000000002",
        provider="openai",
        base_url="https://example.com/v1",
        api_key="secret",
        model="vision-model",
        effort="low",
    )
    store = RoleStore(tmp_path)
    store.create_role(
        name="Mira",
        system_prompt="mira",
        role_id="mira",
        runtime_config={"dialogue_model_registration_id": dialogue.id},
    )
    runtime = RoleModelRuntime(
        role_store=store,
        registrations=[dialogue, visual],
    )

    role = store.get_role("mira")
    assert role is not None
    store.update_role(
        "mira",
        runtime_config={
            **role.runtime_config,
            "dialogue_model_effort": "high",
            "visual_model_effort": "max",
            "visual_model_registration_id": visual.id,
        },
    )

    snapshot = runtime.resolve("mira", "chat")
    assert snapshot.effort == "high"
    assert snapshot.provider._extra_body == {"reasoning_effort": "high"}

    visual_snapshot = runtime.resolve("mira", "vision")
    assert visual_snapshot.effort == "max"
    assert visual_snapshot.provider._extra_body == {"reasoning_effort": "max"}


@pytest.mark.parametrize(
    "provider_name,model,main_extra,auxiliary_extra,main_effort",
    [
        (
            "deepseek",
            "deepseek-v4-flash",
            None,
            {"thinking": {"type": "disabled"}},
            "high",
        ),
        (
            "dashscope",
            "qwen3",
            {"reasoning_effort": "high"},
            {"enable_thinking": False},
            None,
        ),
        ("openai", "generic-model", {"reasoning_effort": "high"}, None, None),
    ],
)
async def test_auxiliary_call_preserves_role_snapshot_and_main_reasoning(
    tmp_path,
    monkeypatch,
    provider_name,
    model,
    main_extra,
    auxiliary_extra,
    main_effort,
):
    create = AsyncMock(
        return_value=SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="ok", tool_calls=[]),
                    finish_reason="stop",
                )
            ]
        )
    )
    monkeypatch.setattr(
        "agent.provider.AsyncOpenAI",
        lambda **_: SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create))
        ),
    )
    store = RoleStore(tmp_path)
    store.create_role(
        name="Mira",
        system_prompt="mira",
        role_id="mira",
        runtime_config={
            "dialogue_model_registration_id": "selected",
            "dialogue_model_effort": "high",
        },
    )
    runtime = RoleModelRuntime(
        role_store=store,
        registrations=[
            replace(registration("selected", model), provider=provider_name)
        ],
    )
    fallback = AsyncMock(spec=LLMProvider)
    provider = RoleAwareProvider(fallback)

    with runtime.activate("mira", "chat") as snapshot:
        for purpose in ("default", "auxiliary", "default"):
            await provider.chat(
                messages=[{"role": "user", "content": "你好"}],
                tools=[],
                model="fallback-model",
                max_tokens=8192,
                # Proactive/drift legacy flags must still respect role effort.
                disable_thinking=True,
                extra_body={"reasoning_effort": "low"},
                call_purpose=purpose,
                auxiliary_max_tokens=512,
            )
        assert snapshot.provider._extra_body == {"reasoning_effort": "high"}
        assert runtime.resolve("mira", "chat").provider is snapshot.provider

    main_before, auxiliary, main_after = [
        call.kwargs for call in create.await_args_list
    ]
    assert main_before == main_after
    assert main_before.get("extra_body") == main_extra
    assert main_before.get("reasoning_effort") == main_effort
    assert main_before["max_tokens"] == 8192
    assert auxiliary.get("extra_body") == auxiliary_extra
    assert auxiliary["max_tokens"] == (8192 if provider_name == "openai" else 512)
    assert "reasoning_effort" not in auxiliary
    assert auxiliary["model"] == model
    assert "call_purpose" not in auxiliary
    fallback.chat.assert_not_awaited()


async def test_role_aware_provider_forwards_fallback_call_options():
    fallback = AsyncMock(spec=LLMProvider)
    provider = RoleAwareProvider(fallback)
    options = dict(
        messages=[{"role": "user", "content": "hi"}],
        tools=[],
        model="fallback-model",
        max_tokens=256,
        tool_choice="none",
        extra_body={"reasoning_effort": "high", "temperature": 0.2},
        disable_thinking=True,
        payload_snapshot_enabled=False,
        on_content_delta=None,
        response_format={"type": "json_object"},
        call_purpose="auxiliary",
        auxiliary_max_tokens=128,
    )

    response = await provider.chat(**options)

    fallback.chat.assert_awaited_once_with(**options)
    assert response is fallback.chat.return_value
