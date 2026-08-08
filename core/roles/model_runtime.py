from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Awaitable, Callable, Generator, Literal

from agent.config_models import ModelRegistration
from agent.provider import LLMProvider, LLMResponse, StreamDelta

from .store import RoleStore

ModelPurpose = Literal["chat", "vision"]


@dataclass(frozen=True)
class RoleModelSnapshot:
    """Immutable provider and model selection captured at turn start."""

    registration_id: str
    registration_name: str
    provider: LLMProvider
    model: str
    effort: str


_current_snapshot: ContextVar[RoleModelSnapshot | None] = ContextVar(
    "role_model_snapshot",
    default=None,
)


class RoleModelRuntime:
    """Resolves one role-owned model choice into a per-turn provider snapshot."""

    def __init__(
        self,
        *,
        role_store: RoleStore,
        registrations: list[ModelRegistration],
        system_prompt: str,
        dev_mode: bool = False,
    ) -> None:
        if not registrations:
            raise ValueError("至少需要一个模型注册")
        self._roles = role_store
        self._registrations = {item.id: item for item in registrations}
        self._first_registration_id = registrations[0].id
        self._system_prompt = system_prompt
        self._dev_mode = dev_mode

    @property
    def first_registration_id(self) -> str:
        """Returns the default dialogue registration for newly created roles."""

        return self._first_registration_id

    def resolve(self, role_id: str, purpose: ModelPurpose) -> RoleModelSnapshot:
        """Captures the role selection once for chat or image-bearing input."""

        role = self._roles.get_role(role_id)
        if role is None:
            raise KeyError(f"role 不存在: {role_id}")
        dialogue_id = str(
            role.runtime_config.get("dialogue_model_registration_id") or ""
        ).strip()
        selected_id = dialogue_id
        if purpose == "vision":
            selected_id = str(
                role.runtime_config.get("visual_model_registration_id") or ""
            ).strip() or dialogue_id
        if not selected_id:
            raise ValueError(f"角色未选择对话模型: {role_id}")
        registration = self._registrations.get(selected_id)
        if registration is None:
            raise ValueError(f"角色引用了不存在的模型注册: {selected_id}")
        extra_body = (
            {}
            if registration.effort == "none"
            else {"reasoning_effort": registration.effort}
        )
        provider = LLMProvider(
            api_key=registration.api_key,
            base_url=registration.base_url,
            system_prompt=self._system_prompt,
            extra_body=extra_body,
            provider_name=registration.provider,
            payload_snapshot_enabled=self._dev_mode,
        )
        return RoleModelSnapshot(
            registration_id=registration.id,
            registration_name=registration.name,
            provider=provider,
            model=registration.model,
            effort=registration.effort,
        )

    @contextmanager
    def activate(self, role_id: str, purpose: ModelPurpose) -> Generator[RoleModelSnapshot]:
        """Keeps one resolved selection stable for the complete async turn."""

        snapshot = self.resolve(role_id, purpose)
        token = _current_snapshot.set(snapshot)
        try:
            yield snapshot
        finally:
            _current_snapshot.reset(token)


class RoleAwareProvider(LLMProvider):
    """Delegates model calls to the active role snapshot when one is present."""

    def __init__(self, fallback: LLMProvider) -> None:
        self._fallback = fallback

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict],
        model: str,
        max_tokens: int,
        tool_choice: str | dict = "auto",
        extra_body: dict | None = None,
        disable_thinking: bool = False,
        payload_snapshot_enabled: bool | None = None,
        on_content_delta: Callable[[StreamDelta], Awaitable[None]] | None = None,
    ) -> LLMResponse:
        snapshot = _current_snapshot.get()
        provider = snapshot.provider if snapshot is not None else self._fallback
        resolved_model = snapshot.model if snapshot is not None else model
        return await provider.chat(
            messages=messages,
            tools=tools,
            model=resolved_model,
            max_tokens=max_tokens,
            tool_choice=tool_choice,
            extra_body=None if snapshot is not None else extra_body,
            disable_thinking=False if snapshot is not None else disable_thinking,
            payload_snapshot_enabled=payload_snapshot_enabled,
            on_content_delta=on_content_delta,
        )
