"""``HostProactiveRunner``: the process-wide ``PROACTIVE_HOST``.

One runner serves every generation. Work that runs or delivers pins the
published generation; reads use the current lease when there is one, otherwise
the published generation, and do not wait. A caller that already holds a lease
keeps that lease. Natural replies, tools and reads live in sibling modules;
this class pins the generation and hands them its core.
"""

from __future__ import annotations

import weakref
from collections.abc import Awaitable, Callable, Mapping, Sequence
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, AsyncIterator, Literal

from agent.core.prompt_block import build_role_user_identities_prompt
from agent.proactive_host import files as host_files
from agent.proactive_host import natural, reads
from agent.proactive_host import tools as host_tools
from agent.provider import LLMProvider, thinking_disabled_provider
from agent.turns.orchestrator import TurnOrchestrator
from agent.turns.proactive_sequence import current_proactive_reply
from agent.turns.reply_interruption import reply_was_invalidated
from conversation.service import desktop_chat_id, desktop_thread_id
from agent.tools.turn_scope import tool_turn_scope
from agent.tools.web_fetch import WebFetchTool
from core.common.channel_directory import DESKTOP_CHANNEL
from core.common.runtime_scope import bind_runtime, current_runtime_lease
from core.error_context import current_session_key
from core.roles.model_runtime import RoleAwareProvider
from core.roles.reply_state import validate_role_reply
from core.roles.role_prompt_compiler import RolePromptCompiler
from session.manager.helpers import role_id_from_session_key, role_session_key
from shiori_sdk.core.conversation import InitiatedDelivery, InitiatedReply
from shiori_sdk.core.proactive_host import (
    CandidateChat,
    CompletionToolCall,
    ModelCompletion,
    NaturalReplyTicket,
    ProactiveHistoryMessage,
    ProactiveToolCall,
    ProactiveToolInvoker,
    ProactiveToolOutcome,
    RecentTurnMessage,
    ValidatedRoleReply,
)
from shiori_sdk.tools import ToolResult

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
        # One provider per generation ``complete`` ran on, keyed by the core's
        # id (``CoreRuntime`` is not hashable) and held weakly, so an old
        # generation's long tick and the new one's ticks can interleave
        # without rebuilding and a retired generation is not kept alive.
        self._completion_providers: dict[int, tuple[weakref.ref[Any], LLMProvider]] = {}

    async def run_tick[T](
        self, role_id: str, operation: Callable[[], Awaitable[T]]
    ) -> T:
        """Run ``operation`` on the role's serial tick gate with the chat model on."""
        token = current_session_key.set(role_session_key(role_id))
        try:
            return await self._run_tick(role_id, operation)
        finally:
            current_session_key.reset(token)

    async def _run_tick[T](
        self, role_id: str, operation: Callable[[], Awaitable[T]]
    ) -> T:
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
            return await host_tools.execute_tool(lease.core, call, invoker)

    async def run_host_tool(
        self, name: str, arguments: Mapping[str, object], *, role_id: str
    ) -> str | ToolResult:
        """Run a registered host tool for ``role_id`` in the role's user context."""
        async with self._pinned() as lease:
            return await host_tools.run_host_tool(
                lease.core, name, arguments, role_id=role_id
            )

    async def deliver(self, reply: InitiatedReply) -> InitiatedDelivery:
        """Deliver through the plan open on this task, or through ``CONVERSATION``."""
        async with self._pinned() as lease:
            if current_proactive_reply() is None:
                return await lease.core.conversation.deliver_initiated_reply(reply)
            return await natural.deliver_through_plan(
                self._orchestrator(lease.core, reply.session_key), reply
            )

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

    def validate_reply(
        self,
        role_id: str,
        *,
        content: str,
        mood: str,
        thought: str,
        allow_empty_content: bool = False,
    ) -> ValidatedRoleReply:
        """Validate one reply against ``CONVERSATION.reply_state`` of this generation."""
        state = self._require_core().conversation.reply_state(role_id)
        reply = validate_role_reply(
            {"content": content, "mood": mood, "thought": thought},
            state.moods,
            allow_empty_content=allow_empty_content,
        )
        return ValidatedRoleReply(
            content=reply.content, mood=reply.mood, thought=reply.thought
        )

    def natural_chat_enabled(self, session_key: str) -> bool:
        """The role record's natural-chat switch, as of this call.

        A missing role is off. The session copy of the role config is not
        the switch. No published generation raises.
        """
        if not role_id_from_session_key(session_key):
            return False
        core = self._require_core()
        return self._orchestrator(core, session_key).natural_chat_enabled(session_key)

    def begin_natural_reply(self) -> NaturalReplyTicket:
        """Issue the ticket one tick invalidates from outside its scope."""
        return natural.HostReplyTicket()

    @asynccontextmanager
    async def natural_reply_scope(
        self,
        ticket: NaturalReplyTicket,
        session_key: str,
        channel: str,
        chat_id: str,
        *,
        turn_id: str,
    ) -> AsyncIterator[None]:
        """Open the tick's plan and commit its tool facts before the plan ends."""
        if not isinstance(ticket, natural.HostReplyTicket):
            raise TypeError("自然回复票据不属于这个端口")
        async with self._pinned() as lease:
            async with natural.natural_reply_scope(
                self._orchestrator(lease.core, session_key),
                ticket,
                session_key,
                channel,
                chat_id,
                turn_id=turn_id,
            ):
                yield

    def reply_invalidated(self) -> bool:
        """Whether the natural reply bound on this task has been superseded."""
        return reply_was_invalidated()

    async def retarget_natural_reply(
        self, session_key: str, target: Mapping[str, object]
    ) -> None:
        """Point the open plan at an explicit account target. No plan does nothing."""
        if current_proactive_reply() is None:
            return
        async with self._pinned() as lease:
            await self._orchestrator(lease.core, session_key).retarget_natural_reply(
                session_key, dict(target)
            )

    async def retarget_natural_transport(
        self, session_key: str, channel: str, chat_id: str
    ) -> None:
        """Point the open plan at another candidate chat. No plan does nothing."""
        if current_proactive_reply() is None:
            return
        async with self._pinned() as lease:
            await natural.retarget_transport(
                self._orchestrator(lease.core, session_key),
                session_key,
                channel,
                chat_id,
            )

    def natural_reply_active(self) -> bool:
        """Whether this task is inside a natural-reply scope that has a plan."""
        return current_proactive_reply() is not None

    def natural_reply_properties(self) -> Mapping[str, object]:
        """The ``messages`` property a natural draft carries instead of its text."""
        return natural.natural_reply_properties()

    def natural_reply_messages(self) -> tuple[str, ...] | None:
        """The messages the open plan accepted from the last natural draft."""
        return natural.natural_reply_messages()

    def candidate_chats(self, role_id: str) -> tuple[CandidateChat, ...]:
        """Desktop first, then private chats with the bound user."""
        return reads.candidate_chats(self._require_core(), role_id)

    def last_user_message_at(
        self, role_id: str, channel: str, chat_id: str
    ) -> datetime | None:
        """When the user last wrote in that chat, or None."""
        return reads.last_user_message_at(
            self._require_core(), role_id, channel, chat_id
        )

    def tool_schemas(
        self, names: Sequence[str] | None = None
    ) -> tuple[Mapping[str, object], ...]:
        """Schemas from the generation's registry, in the requested order."""
        return host_tools.tool_schemas(self._require_core(), names)

    def mcp_server_names(self) -> tuple[str, ...]:
        """MCP servers that currently have tools on the generation, sorted."""
        return host_tools.mcp_server_names(self._require_core())

    def mcp_tool_names(self, server: str) -> tuple[str, ...]:
        """The tools ``server`` currently has on the generation, sorted."""
        return host_tools.mcp_tool_names(self._require_core(), server)

    def require_channel_account(self, role_id: str, channel: str) -> None:
        """Raise unless ``role_id`` has an account on ``channel``."""
        host_tools.require_channel_account(self._require_core(), role_id, channel)

    def recent_messages(
        self, role_id: str, *, limit: int
    ) -> tuple[RecentTurnMessage, ...]:
        """Recent user-context turns on the role session, oldest first."""
        return reads.recent_messages(self._require_core(), role_id, limit=limit)

    def recent_proactive_messages(
        self, role_id: str, *, limit: int = 5
    ) -> tuple[ProactiveHistoryMessage, ...]:
        """The role session's recent proactive messages, oldest first."""
        return reads.recent_proactive_messages(
            self._require_core(), role_id, limit=limit
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
        natural_draft: bool = False,
    ) -> ModelCompletion:
        """One chat completion on the published model.

        The fallback provider forces thinking off. An active role-model
        snapshot (inside ``run_tick``) keeps that model's own effort.
        ``natural_draft`` turns the completion into the open plan's draft
        before it is returned; the plan keeps the provider response.
        """
        if natural_draft and current_proactive_reply() is None:
            raise RuntimeError("自然回复补全需要已打开的回复计划")
        async with self._pinned() as lease:
            config = lease.core.config
            provider = RoleAwareProvider(self._thinking_provider(lease.core))
            payload = [dict(message) for message in messages]
            sent_max = config.max_tokens if max_tokens is None else max_tokens
            response = await provider.chat(
                messages=payload,
                tools=[dict(tool) for tool in tools],
                model=config.model,
                max_tokens=sent_max,
                tool_choice=(
                    tool_choice if isinstance(tool_choice, str) else dict(tool_choice)
                ),
                disable_thinking=disable_thinking,
                call_purpose=call_purpose,
                defer_tool_argument_errors=defer_tool_argument_errors,
            )
            if natural_draft:
                response = await natural.complete_natural_draft(
                    response,
                    messages=payload,
                    provider=provider,
                    model=config.model,
                    max_tokens=sent_max,
                )
        return ModelCompletion(
            content=response.content or "",
            tool_calls=tuple(
                CompletionToolCall(
                    id=call.id,
                    name=call.name,
                    arguments=dict(call.arguments),
                    raw_arguments=call.raw_arguments,
                    arguments_error=call.arguments_error,
                )
                for call in (response.tool_calls or [])
            ),
            thinking=response.thinking,
        )

    def file_tool_schema(self, name: str) -> dict[str, Any]:
        """Schema of a host file tool."""
        return host_files.file_tool_schema(name)

    async def run_drift_file_tool(
        self, role_id: str, name: str, arguments: Mapping[str, object]
    ) -> str | ToolResult:
        """Run a file tool for the role's Drift, confined to its drift directory."""
        workspace = self._require_core().session_manager.workspace
        return await host_files.run_drift_file_tool(
            workspace, role_id, name, dict(arguments)
        )

    def web_fetch_available(self) -> bool:
        """False when the host web fetch tool cannot be constructed."""
        try:
            _ = WebFetchTool()
        except RuntimeError:
            return False
        return True

    async def fetch_url(self, url: str, *, format: str = "text") -> str:
        """Fetch ``url`` through the host web fetch tool."""
        result = await WebFetchTool().execute(url=url, format=format)
        return str(result)

    def tool_resource_scope(self):
        """The host tool-turn scope, shared with passive turns."""
        return tool_turn_scope()

    def configured_max_tokens(self) -> int:
        """The visible generation's configured completion cap."""
        return int(self._require_core().config.max_tokens)

    def _thinking_provider(self, core: Any) -> LLMProvider:
        """The thinking-disabled provider for ``core``'s config, owned by ``core``.

        Built once per generation and registered on its ``additional_providers``
        so it closes when that generation closes, after its leases drain.
        """
        cached = self._completion_providers.get(id(core))
        if cached is not None and cached[0]() is core:
            return cached[1]
        provider = thinking_disabled_provider(core.config, core.provider)
        if provider is not core.provider:
            core.additional_providers.append(provider)
        key = id(core)
        self._completion_providers[key] = (weakref.ref(core), provider)
        # Drop the entry with the generation, so its id cannot be reused.
        weakref.finalize(core, self._completion_providers.pop, key, None)
        return provider

    @staticmethod
    def _orchestrator(core: Any, session_key: str) -> TurnOrchestrator:
        """The generation's delivery wiring for the role owning ``session_key``."""
        role_id = role_id_from_session_key(session_key)
        if not role_id:
            raise ValueError(f"主动回复只接受角色会话: {session_key}")
        return core.conversation.orchestrator(role_id)

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
