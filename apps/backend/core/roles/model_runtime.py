from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Awaitable, Callable, Generator, Literal

from agent.config_models import ModelRegistration
from agent.provider import LLMCallPurpose, LLMProvider, LLMResponse, StreamDelta

from .store import RoleStore
from .model_errors import ModelConfigurationError, incomplete_registration_fields

ModelPurpose = Literal["chat", "vision"]
_VALID_EFFORTS = {"none", "low", "high", "max"}


@dataclass(frozen=True)
class RoleModelSnapshot:
    """Immutable provider and model selection captured at turn start."""

    registration_id: str
    provider: LLMProvider
    model: str
    effort: str
    role_id: str = ""
    purpose: ModelPurpose = "chat"


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
        dev_mode: bool = False,
    ) -> None:
        self._roles = role_store
        self._registrations = {item.id: item for item in registrations}
        self._dev_mode = dev_mode
        self._providers: dict[tuple[str, str], LLMProvider] = {}

    def resolve(self, role_id: str, purpose: ModelPurpose) -> RoleModelSnapshot:
        """Captures the role selection once for chat or image-bearing input."""
        registration = self._selected_registration(role_id, purpose)
        role = self._roles.get_role(role_id)
        if role is None:
            raise KeyError(f"role 不存在: {role_id}")
        effort = registration.effort
        effort_key = f"{'dialogue' if purpose == 'chat' else 'visual'}_model_effort"
        role_effort = str(role.runtime_config.get(effort_key) or "").strip().lower()
        if role_effort in _VALID_EFFORTS:
            effort = role_effort
        extra_body = {} if effort == "none" else {"reasoning_effort": effort}
        key = (registration.id, effort)
        provider = self._providers.get(key)
        if provider is None:
            provider = LLMProvider(
                api_key=registration.api_key,
                base_url=registration.base_url,
                extra_body=extra_body,
                provider_name=registration.provider,
                payload_snapshot_enabled=self._dev_mode,
            )
            self._providers[key] = provider
        return RoleModelSnapshot(
            registration_id=registration.id,
            provider=provider,
            model=registration.model,
            effort=effort,
            role_id=role_id,
            purpose=purpose,
        )

    def availability(self, role_id: str, purpose: ModelPurpose = "chat"):
        """Reports configuration availability without instantiating a provider."""
        try:
            registration = self._selected_registration(role_id, purpose)
        except ModelConfigurationError as error:
            return {"available": False, **error.to_details()}
        return {"available": True, "registration_id": registration.id}

    async def aclose(self) -> None:
        """Closes providers after all tasks holding this generation have drained."""
        providers = list(self._providers.values())
        self._providers.clear()
        for provider in providers:
            await provider.aclose()

    def _selected_registration(self, role_id: str, purpose: ModelPurpose):
        role = self._roles.get_role(role_id)
        if role is None:
            raise KeyError(f"role 不存在: {role_id}")
        if not self._registrations:
            raise ModelConfigurationError(
                reason="no_models", role_id=role_id, purpose=purpose
            )
        dialogue_id = str(
            role.runtime_config.get("dialogue_model_registration_id") or ""
        ).strip()
        selected_id = dialogue_id
        if purpose == "vision":
            selected_id = (
                str(
                    role.runtime_config.get("visual_model_registration_id") or ""
                ).strip()
                or dialogue_id
            )
        if not selected_id:
            raise ModelConfigurationError(
                reason="role_unbound", role_id=role_id, purpose=purpose
            )
        registration = self._registrations.get(selected_id)
        if registration is None:
            raise ModelConfigurationError(
                reason="registration_missing",
                role_id=role_id,
                purpose=purpose,
                registration_id=selected_id,
            )
        fields = incomplete_registration_fields(registration)
        if fields:
            raise ModelConfigurationError(
                reason="connection_incomplete",
                role_id=role_id,
                purpose=purpose,
                registration_id=selected_id,
                fields=fields,
            )
        return registration

    @contextmanager
    def activate(
        self, role_id: str, purpose: ModelPurpose
    ) -> Generator[RoleModelSnapshot]:
        """Keeps one resolved selection stable for the complete async turn."""

        snapshot = _current_snapshot.get()
        if (
            snapshot is None
            or snapshot.role_id != role_id
            or snapshot.purpose != purpose
        ):
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
        response_format: dict[str, str] | None = None,
        call_purpose: LLMCallPurpose = "default",
        auxiliary_max_tokens: int | None = None,
    ) -> LLMResponse:
        """Keeps role effort for default calls and permits explicit auxiliary work."""
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
            # Legacy flags in role-speaking paths (including proactive/drift)
            # do not override role effort. Auxiliary purpose is preserved separately.
            disable_thinking=False if snapshot is not None else disable_thinking,
            payload_snapshot_enabled=payload_snapshot_enabled,
            on_content_delta=on_content_delta,
            **({"response_format": response_format} if response_format else {}),
            call_purpose=call_purpose,
            auxiliary_max_tokens=auxiliary_max_tokens,
        )
