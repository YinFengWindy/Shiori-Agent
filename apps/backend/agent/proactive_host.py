"""``PROACTIVE_HOST``: the host services a proactive tick calls.

One runner serves every generation. Work that runs or delivers pins the
published generation; reads use the current lease when there is one, otherwise
the published generation, and do not wait. A caller that already holds a lease
keeps that lease.
"""

from __future__ import annotations

import weakref
from collections.abc import Awaitable, Callable, Mapping, Sequence
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, AsyncIterator, Literal

from agent.core.prompt_block import build_role_user_identities_prompt
from agent.initiated_delivery import orchestrator_for
from agent.provider import LLMProvider, thinking_disabled_provider
from agent.tools.account_delivery import shared_account_delivery
from agent.tools.execution import ToolExecutionRequest, ToolExecutor
from agent.turns.proactive_sequence import current_proactive_reply
from agent.turns.reply_interruption import (
    ReplyInterruption,
    ReplyPlanInvalidated,
    reply_was_invalidated,
)
from conversation.context_scope import user_context_view
from conversation.initiated import _turn_result
from conversation.service import desktop_chat_id, desktop_thread_id
from core.common.channel_directory import DESKTOP_CHANNEL
from core.common.runtime_scope import bind_runtime, current_runtime_lease
from core.roles.bound_chats import bound_chat_target, role_bound_chats
from core.roles.model_runtime import RoleAwareProvider
from core.roles.reply_policy import natural_chat_selected
from core.roles.reply_state import role_mood_catalog, validate_role_reply
from core.roles.role_prompt_compiler import RolePromptCompiler
from core.roles.services import RoleSessionService
from session.manager.helpers import role_id_from_session_key, role_session_key
from shiori_sdk.accounts.targets import AccountTarget
from shiori_sdk.channels.threads import network_thread_id
from shiori_sdk.core.conversation import InitiatedDelivery, InitiatedReply
from shiori_sdk.core.proactive_host import (
    CandidateChat,
    CompletionToolCall,
    ModelCompletion,
    NaturalReplyInvalidated,
    NaturalReplyTicket,
    ProactiveHistoryMessage,
    ProactiveToolCall,
    ProactiveToolInvoker,
    ProactiveToolOutcome,
    RecentTurnMessage,
    RoleReplyState,
    ValidatedRoleReply,
)
from shiori_sdk.prompting import is_context_frame

_RUNTIME_REQUIRED = "主动端口需要已启动的运行时"


def _parse_timestamp(raw: object) -> datetime | None:
    """ISO timestamp, or None. A naive legacy value was local time."""
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=datetime.now().astimezone().tzinfo)
    return parsed


class _NaturalReplyTicket:
    """The ticket ``begin_natural_reply`` issues. Other objects are refused."""

    def __init__(self) -> None:
        self.interruption = ReplyInterruption()

    def invalidate(self) -> None:
        self.interruption.invalidate()


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

    def natural_chat_enabled(self, session_key: str) -> bool:
        """The role record's natural-chat switch, as of this call.

        A missing role is off. The session copy of the role config is not
        the switch. No published generation raises.
        """
        role_id = role_id_from_session_key(session_key)
        if not role_id:
            return False
        store = self._require_core().role_runtime_registry.repository.store
        return natural_chat_selected(store.get_role(role_id))

    def begin_natural_reply(self) -> NaturalReplyTicket:
        """Issue the ticket one tick invalidates from outside its scope."""
        return _NaturalReplyTicket()

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
        """Open the tick's plan and commit its tool facts before the plan ends.

        Facts are committed while the plan is still current, including when
        the body raises ``NaturalReplyInvalidated``.
        """
        if not isinstance(ticket, _NaturalReplyTicket):
            raise TypeError("自然回复票据不属于这个端口")
        role_id = self._role_id(session_key)
        async with self._pinned() as lease:
            orchestrator = self._orchestrator(lease.core, role_id)
            async with orchestrator.natural_reply_scope(
                session_key,
                channel,
                chat_id,
                turn_id=turn_id,
                interruption=ticket.interruption,
            ):
                try:
                    yield
                except ReplyPlanInvalidated as exc:
                    raise NaturalReplyInvalidated(str(exc)) from exc
                finally:
                    await orchestrator.commit_proactive_tool_facts(session_key)

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
            await self._orchestrator(
                lease.core, self._role_id(session_key)
            ).retarget_natural_reply(session_key, dict(target))

    async def retarget_natural_transport(
        self, session_key: str, channel: str, chat_id: str
    ) -> None:
        """Point the open plan at another candidate chat. No plan does nothing."""
        if current_proactive_reply() is None:
            return
        async with self._pinned() as lease:
            await self._orchestrator(
                lease.core, self._role_id(session_key)
            ).retarget_natural_transport(session_key, channel, chat_id)

    def natural_reply_active(self) -> bool:
        """Whether this task is inside a natural-reply scope that has a plan."""
        return current_proactive_reply() is not None

    async def commit_natural_reply(self, reply: InitiatedReply) -> InitiatedDelivery:
        """Deliver through the plan already open on this task.

        Does not open another scope. The committed event is emitted before
        this returns; the caller's success and failure effects follow it.
        """
        if current_proactive_reply() is None:
            raise RuntimeError("自然回复序列需要已打开的回复作用域")
        async with self._pinned() as lease:
            committed: list[str] = []
            complete = await self._orchestrator(
                lease.core, self._role_id(reply.session_key)
            ).handle_proactive_turn(
                result=_turn_result(reply, include_target=False),
                session_key=reply.session_key,
                channel=reply.channel,
                chat_id=reply.chat_id,
                source=reply.source,
                committed=committed,
            )
            return InitiatedDelivery(message_ids=tuple(committed), complete=complete)

    def candidate_chats(self, role_id: str) -> tuple[CandidateChat, ...]:
        """Desktop first, then private chats with the bound user.

        Does not consult the proactive switch. A missing role raises ``KeyError``.
        """
        store = self._require_core().role_runtime_registry.repository.store
        if store.get_role(role_id) is None:
            raise KeyError(f"角色不存在: {role_id}")
        return (
            CandidateChat(channel=DESKTOP_CHANNEL, chat_id=desktop_chat_id(role_id)),
            *(
                CandidateChat(channel=chat.channel, chat_id=chat.chat_id)
                for _, _, chat in role_bound_chats(store, role_id)
            ),
        )

    def last_user_message_at(
        self, role_id: str, channel: str, chat_id: str
    ) -> datetime | None:
        """When the user last wrote in that chat, or None.

        A naive legacy timestamp was written in local time and is converted.
        """
        raw = self._require_core().session_manager.conversation_store.last_user_message_at(
            network_thread_id(role_id, channel, chat_id)
        )
        if raw is None:
            return None
        return datetime.fromisoformat(raw).astimezone()

    def bound_chat_target(
        self, role_id: str, channel: str, chat_id: str
    ) -> tuple[str, AccountTarget]:
        """The account plugin and private target that reach a bound user's chat."""
        store = self._require_core().role_runtime_registry.repository.store
        return bound_chat_target(store, role_id, channel, chat_id)

    def tool_schemas(
        self, names: Sequence[str] | None = None
    ) -> tuple[Mapping[str, object], ...]:
        """Schemas from the generation's registry, in the requested order."""
        selected = None if names is None else list(names)
        return tuple(self._require_core().tools.get_schemas(selected))

    def mcp_server_names(self) -> tuple[str, ...]:
        """MCP servers that currently have tools on the generation, sorted."""
        return tuple(sorted(self._require_core().tools.get_mcp_server_names()))

    def require_channel_account(self, role_id: str, channel: str) -> None:
        """Raise unless ``role_id`` has an account on ``channel``."""
        delivery = shared_account_delivery(self._require_core().tools)
        if delivery is None:
            raise RuntimeError("账号目标发送服务不可用")
        delivery.channel_account(channel, role_id)

    def recent_messages(
        self, role_id: str, *, limit: int
    ) -> tuple[RecentTurnMessage, ...]:
        """Recent user-context turns on the role session, oldest first."""
        core = self._require_core()
        session = core.session_manager.get_or_create(role_session_key(role_id))
        view = user_context_view(core.session_manager.workspace, role_id)
        messages = session.history_window(limit, include=view.includes)
        results: list[RecentTurnMessage] = []
        for message in messages:
            if message.get("role") not in ("user", "assistant"):
                continue
            if not message.get("content"):
                continue
            content = str(message.get("content", ""))
            if is_context_frame(content):
                continue
            results.append(
                RecentTurnMessage(
                    role=str(message["role"]),
                    content=content[:200],
                    timestamp=str(message.get("timestamp", "")),
                )
            )
        return tuple(results)

    def recent_proactive_messages(
        self, role_id: str, *, limit: int = 5
    ) -> tuple[ProactiveHistoryMessage, ...]:
        """The role session's recent proactive messages, oldest first."""
        session = self._require_core().session_manager.get_or_create(
            role_session_key(role_id)
        )
        found: list[ProactiveHistoryMessage] = []
        for message in reversed(session.messages):
            if message.get("role") != "assistant":
                continue
            if not message.get("proactive") or not message.get("content"):
                continue
            refs = tuple(
                ref
                for ref in message.get("source_refs") or []
                if isinstance(ref, Mapping)
            )
            found.append(
                ProactiveHistoryMessage(
                    content=str(message["content"]),
                    timestamp=_parse_timestamp(message.get("timestamp")),
                    state_summary_tag=str(
                        message.get("state_summary_tag", "none") or "none"
                    ),
                    source_refs=refs,
                )
            )
            if len(found) >= limit:
                break
        return tuple(reversed(found))

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
        ``natural_draft`` runs the open plan's format correction before the
        completion is returned; the plan keeps the provider response.
        """
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
                if current_proactive_reply() is None:
                    raise RuntimeError("自然回复补全需要已打开的回复作用域")
                from proactive_v2.reply_output import complete_natural_push

                response = await complete_natural_push(
                    response,
                    messages=payload,
                    provider=provider,
                    model=config.model,
                    max_tokens=sent_max,
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

    def _role_id(self, session_key: str) -> str:
        role_id = role_id_from_session_key(session_key)
        if not role_id:
            raise ValueError(f"主动回复只接受角色会话: {session_key}")
        return role_id

    def _orchestrator(self, core: Any, role_id: str):
        return orchestrator_for(
            role_id,
            session_manager=core.session_manager,
            presence=core.presence,
            push_tool=core.push_tool,
            event_bus=core.event_bus,
            tools=core.tools,
            role_store=core.role_runtime_registry.repository.store,
        )

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
