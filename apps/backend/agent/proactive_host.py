"""``PROACTIVE_HOST``: the host services a proactive tick calls.

One runner serves every generation. Work that runs or delivers pins the
published generation; reads use the current lease when there is one, otherwise
the published generation, and do not wait. The proactive loop still calls the
host directly.
"""

from __future__ import annotations

import weakref
from collections.abc import Awaitable, Callable, Mapping, Sequence
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, AsyncIterator, Literal

from agent.core.prompt_block import build_role_user_identities_prompt
from agent.provider import LLMProvider, thinking_disabled_provider
from agent.tools.execution import ToolExecutionRequest, ToolExecutor
from conversation.service import desktop_chat_id, desktop_thread_id
from core.common.channel_directory import DESKTOP_CHANNEL
from core.common.runtime_scope import bind_runtime, current_runtime_lease
from core.roles.model_runtime import RoleAwareProvider
from core.roles.reply_state import role_mood_catalog, validate_role_reply
from core.roles.role_prompt_compiler import RolePromptCompiler
from core.roles.services import RoleSessionService
from session.manager.helpers import role_session_key
from shiori_sdk.core.conversation import InitiatedDelivery, InitiatedReply
from shiori_sdk.core.proactive_host import (
    CompletionToolCall,
    ModelCompletion,
    ProactiveToolCall,
    ProactiveToolInvoker,
    ProactiveToolOutcome,
    RoleReplyState,
    ValidatedRoleReply,
)

_RUNTIME_REQUIRED = "主动端口需要已启动的运行时"


class HostProactiveRunner:
    """Process-wide ``PROACTIVE_HOST``.

    ``runtime_provider`` returns the app runtime (``core``, ``acquire``,
    ``wait_for_admission``, ``desktop_presence``). The thinking-disabled
    provider ``complete`` builds belongs to the generation it was built for
    and closes with it (``additional_providers``).
    """

    def __init__(self, runtime_provider: Callable[[], Any]) -> None:
        self._runtime_provider = runtime_provider
        # The last generation ``complete`` ran on, held weakly so a retired
        # generation is not kept alive, and the provider built for it.
        self._completion_core: weakref.ref[Any] | None = None
        self._completion_provider: LLMProvider | None = None

    async def run_tick[T](
        self, role_id: str, operation: Callable[[], Awaitable[T]]
    ) -> T:
        """Run ``operation`` on the role's serial tick gate with the chat model on."""
        async with self._pinned() as lease:
            registry = lease.core.role_runtime_registry
            context = registry.create_context(
                role_id=role_id,
                thread_id=desktop_thread_id(role_id),
                transport_channel=DESKTOP_CHANNEL,
                transport_chat_id=desktop_chat_id(role_id),
                source="proactive",
                work_kind="proactive_tick",
            )

            async def run_with_model_snapshot() -> T:
                runtime = await registry.get(role_id)
                with runtime.activate_model("chat"):
                    return await operation()

            return await registry.dispatch_proactive_tick(
                context, run_with_model_snapshot
            )

    def passive_turn_busy(self, role_id: str) -> bool:
        """Whether a passive turn currently holds ``role:<id>``.

        False when the runtime is down. This does not wait for admission.
        """
        core = self._visible_core()
        if core is None:
            return False
        state = getattr(getattr(core, "loop", None), "processing_state", None)
        if state is None:
            return False
        return bool(state.is_busy(role_session_key(role_id)))

    async def execute_tool(
        self, call: ProactiveToolCall, invoker: ProactiveToolInvoker
    ) -> ProactiveToolOutcome:
        """Run one tool call through the published kernel's checks."""
        async with self._pinned() as lease:
            manager = lease.core.plugin_manager
            if manager is None:
                raise RuntimeError("主动工具需要已启动的插件内核")
            executor = ToolExecutor(lambda: manager.kernel)

            async def run(name: str, arguments: dict[str, Any]) -> object:
                return await invoker(name, arguments)

            result = await executor.execute(
                ToolExecutionRequest(
                    call_id=call.call_id,
                    tool_name=call.name,
                    arguments=dict(call.arguments),
                    source="proactive",
                    session_key=call.session_key,
                    channel=call.channel,
                    chat_id=call.chat_id,
                ),
                run,
            )
            # The text the host's proactive and Drift tool loops record.
            return ProactiveToolOutcome(
                text=str(result.output),
                status=result.status,
                arguments=result.final_arguments,
                finalize=result.finalize,
            )

    async def deliver(self, reply: InitiatedReply) -> InitiatedDelivery:
        """Deliver ``reply`` through the published generation's ``CONVERSATION``."""
        async with self._pinned() as lease:
            return await lease.core.conversation.deliver_initiated_reply(reply)

    def user_at_desktop(self) -> bool:
        """The process-wide desktop presence report."""
        runtime = self._runtime_provider()
        if runtime is None:
            raise RuntimeError(_RUNTIME_REQUIRED)
        presence = getattr(runtime, "desktop_presence", None)
        if presence is None:
            raise RuntimeError(_RUNTIME_REQUIRED)
        return bool(presence.is_desktop_present())

    def recent_activity(self, role_id: str, *, now: datetime) -> str:
        """External-thread activity visible to ``role_id`` at ``now``."""
        return self._require_core().group_environment.render_recent_activity(
            role_id, now=now
        )

    def compile_role_prompt(self, role_id: str) -> str:
        """The role prompt a proactive turn uses, read from the published store."""
        store = self._require_core().role_runtime_registry.repository.store
        role = store.get_role(role_id)
        if role is None:
            raise ValueError(f"role not found for proactive generation: {role_id}")
        prompt = RolePromptCompiler().compile(role).content.strip()
        if not prompt:
            raise ValueError(f"role.system_prompt required: {role_id}")
        identities = build_role_user_identities_prompt(role_id, store)
        return f"{prompt}\n\n{identities}" if identities else prompt

    def reply_state(self, role_id: str) -> RoleReplyState:
        """Moods and the stored mood timestamp, from the role's session."""
        session = self._open_role_session(role_id)
        return RoleReplyState(
            moods=role_mood_catalog(session.metadata.get("role_runtime_config", {})),
            mood_updated_at=str(session.metadata.get("current_mood_updated_at", "")),
        )

    def validate_reply(
        self,
        role_id: str,
        *,
        content: str,
        mood: str,
        thought: str,
        allow_empty_content: bool = False,
    ) -> ValidatedRoleReply:
        """Validate one reply against the role's mood catalog."""
        state = self.reply_state(role_id)
        reply = validate_role_reply(
            {"content": content, "mood": mood, "thought": thought},
            state.moods,
            allow_empty_content=allow_empty_content,
        )
        return ValidatedRoleReply(
            content=reply.content, mood=reply.mood, thought=reply.thought
        )

    async def complete(
        self,
        messages: Sequence[Mapping[str, object]],
        *,
        tools: Sequence[Mapping[str, object]] = (),
        tool_choice: str | Mapping[str, object] = "auto",
        max_tokens: int | None = None,
        call_purpose: Literal["default", "auxiliary"] = "default",
        disable_thinking: bool = True,
        defer_tool_argument_errors: bool = False,
    ) -> ModelCompletion:
        """One chat completion on the published model.

        The fallback provider forces thinking off. An active role-model
        snapshot (inside ``run_tick``) keeps that model's own effort.
        """
        async with self._pinned() as lease:
            config = lease.core.config
            provider = RoleAwareProvider(self._thinking_provider(lease.core))
            response = await provider.chat(
                messages=[dict(message) for message in messages],
                tools=[dict(tool) for tool in tools],
                model=config.model,
                max_tokens=config.max_tokens if max_tokens is None else max_tokens,
                tool_choice=(
                    tool_choice if isinstance(tool_choice, str) else dict(tool_choice)
                ),
                disable_thinking=disable_thinking,
                call_purpose=call_purpose,
                defer_tool_argument_errors=defer_tool_argument_errors,
            )
        calls = tuple(
            CompletionToolCall(
                id=call.id,
                name=call.name,
                arguments=dict(call.arguments),
                raw_arguments=call.raw_arguments,
                arguments_error=call.arguments_error,
            )
            for call in (response.tool_calls or [])
        )
        return ModelCompletion(
            content=response.content or "",
            tool_calls=calls,
            thinking=response.thinking,
        )

    def _thinking_provider(self, core: Any) -> LLMProvider:
        """The thinking-disabled provider for ``core``'s config, owned by ``core``.

        Built once per generation and registered on its ``additional_providers``
        so it closes when that generation closes, after its leases drain.
        """
        if self._completion_core is not None and self._completion_core() is core:
            assert self._completion_provider is not None
            return self._completion_provider
        provider = thinking_disabled_provider(core.config, core.provider)
        if provider is not core.provider:
            core.additional_providers.append(provider)
        self._completion_core = weakref.ref(core)
        self._completion_provider = provider
        return provider

    def _open_role_session(self, role_id: str):
        core = self._require_core()
        role = core.role_runtime_registry.repository.store.get_role(role_id)
        if role is None:
            raise ValueError(f"role not found for proactive generation: {role_id}")
        return RoleSessionService(core.session_manager).open_by_role(role)

    def _visible_core(self) -> Any:
        lease = current_runtime_lease()
        if lease is not None:
            return lease.core
        runtime = self._runtime_provider()
        if runtime is None:
            return None
        return getattr(runtime, "core", None)

    def _require_core(self) -> Any:
        core = self._visible_core()
        if core is None:
            raise RuntimeError(_RUNTIME_REQUIRED)
        return core

    @asynccontextmanager
    async def _pinned(self) -> AsyncIterator[Any]:
        current = current_runtime_lease()
        if current is not None:
            yield current
            return
        runtime = self._runtime_provider()
        if runtime is None:
            raise RuntimeError(_RUNTIME_REQUIRED)
        await runtime.wait_for_admission()
        lease = runtime.acquire()
        async with lease:
            with bind_runtime(lease):
                yield lease
