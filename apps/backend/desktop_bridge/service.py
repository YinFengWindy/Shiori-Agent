from __future__ import annotations

from agent.plugin_host.bridge_events import PluginBridgeEvent, PluginRpcError

from contextlib import ExitStack
from core.accounts import AccountDeletingError, AccountNotFoundError
from core.common.channel_directory import DESKTOP_CHANNEL
from core.common.cleanup import run_cleanup_steps
from core.common.task_collector import TaskCollector

import inspect
import logging
from contextvars import Context
from collections.abc import Awaitable, Callable
from typing import Any

from agent.looping.core import AgentLoop
from agent.plugin_host.rpc import PluginRpcRegistry
from agent.tools.message_push import MessagePushTool
from agent.turns.turn_pushes import current_turn_pushes
from bus.event_bus import EventBus
from bus.events_lifecycle import (
    ProactiveMessageCommitted,
    RoleDeleted,
    TurnCommitted,
)
from conversation.service import ConversationService
from core.memory.group_environment import GroupEnvironment
from core.memory.member_profiles import MemberProfiles
from core.roles import (
    RoleAggregateService,
    RoleRelationshipRuntimeService,
    RoleStore,
)
from core.roles.role_runtime import RoleRuntimeRegistry
from core.roles.model_runtime import ModelConfigurationError, RoleModelRuntime
from desktop_bridge.app_service import DesktopAppService
from desktop_bridge.account_requests import DesktopAccountRequestHandler
from desktop_bridge.identity_requests import DesktopIdentityRequestHandler
from desktop_bridge.chat_requests import DesktopChatRequestHandler
from desktop_bridge.chat_service import ChatTurnBusyError, DesktopChatService
from desktop_bridge.method_policy import MethodPolicy, resolve_plugin_method_policy
from desktop_bridge.models import BridgeError, BridgeEvent, BridgeResponse
from desktop_bridge.phone_memory_requests import DesktopPhoneMemoryRequestHandler
from desktop_bridge.phone_requests import (
    PHONE_CONVERSATION_UPDATED,
    DesktopPhoneRequestHandler,
)
from desktop_bridge.plugin_requests import DesktopPluginRequestHandler
from desktop_bridge.request_router import DesktopBridgeRequestRouter
from desktop_bridge.role_requests import DesktopRoleRequestHandler
from desktop_bridge.role_card_import_service import DesktopRoleCardImportService
from desktop_bridge.role_presenter import DesktopRolePresenter
from desktop_bridge.role_task_service import RoleTaskService
from desktop_bridge.session_task_requests import DesktopSessionTaskRequestHandler
from desktop_bridge.session_presenter import DesktopSessionPresenter
from desktop_bridge.turn_messages import committed_turn_messages
from desktop_bridge.voice.voice_handler import DesktopVoiceHandler
from agent.voice_config import VoiceConfig
from desktop_bridge.voice.voice_service import VoiceService, VoiceServiceError
from session.manager import Session, SessionManager

logger = logging.getLogger("desktop.bridge")


def _sanitize_voice_metrics(value: object) -> dict[str, str | int] | None:
    if not isinstance(value, dict):
        return None
    provider = str(value.get("provider") or "").strip()
    if not provider:
        return None

    def _non_negative_int(key: str) -> int:
        raw = value.get(key)
        return int(raw) if isinstance(raw, (int, float)) and raw >= 0 else 0

    return {
        "provider": provider,
        "request_id": str(value.get("request_id") or "").strip(),
        "elapsed_ms": _non_negative_int("elapsed_ms"),
        "audio_duration_ms": _non_negative_int("audio_duration_ms"),
        "character_count": _non_negative_int("character_count"),
        "error_code": str(value.get("error_code") or "").strip(),
    }


class DesktopBridgeService:
    def __init__(
        self,
        *,
        workspace,
        role_store: RoleStore,
        session_manager: SessionManager,
        agent_loop: AgentLoop,
        event_bus: EventBus,
        role_service: RoleAggregateService | None = None,
        config: Any = None,
        push_tool: MessagePushTool | None = None,
        relationship_runtime: RoleRelationshipRuntimeService | None = None,
        presence: Any | None = None,
        scheduler: Any | None = None,
        subagent_manager: Any | None = None,
        memory_optimizer: Any | None = None,
        voice_service: VoiceService | None = None,
        role_runtime_registry: RoleRuntimeRegistry | None = None,
        memory_engine: Any | None = None,
        card_import_service: Any | None = None,
        activate_transport: bool = True,
        model_resolver: RoleModelRuntime | None = None,
        plugin_rpc_registry: PluginRpcRegistry | None = None,
        group_environment: GroupEnvironment | None = None,
    ) -> None:
        self.workspace = workspace
        self.role_store = role_store
        self.session_manager = session_manager
        self.agent_loop = agent_loop
        self.event_bus = event_bus
        self._plugin_event_listener = self._on_plugin_event
        self._plugin_event_registry = plugin_rpc_registry
        self.event_bus.on(PluginBridgeEvent, self._plugin_event_listener)
        self._turn_committed_listener = self._on_turn_committed
        self._proactive_message_listener = self._on_proactive_message_committed
        self.event_bus.on(TurnCommitted, self._turn_committed_listener)
        self.event_bus.on(
            ProactiveMessageCommitted,
            self._proactive_message_listener,
        )
        self._account_change_listener = self._on_account_change
        self._identity_change_listener = self._on_identity_change
        self._change_pushes = TaskCollector("Bridge change push")
        role_store.accounts.add_change_listener(self._account_change_listener)
        role_store.identities.add_change_listener(self._identity_change_listener)
        self.config = config
        self.role_runtime_registry = role_runtime_registry
        registrations = getattr(config, "model_registrations", None)
        self._owns_model_resolver = model_resolver is None
        self.model_resolver = model_resolver or (
            RoleModelRuntime(
                role_store=role_store,
                registrations=registrations,
                dev_mode=bool(getattr(config, "dev_mode", False)),
            )
            if isinstance(registrations, list)
            else None
        )
        self.memory_engine = memory_engine
        self._event_listeners: set[
            Callable[[dict[str, Any]], Awaitable[None] | None]
        ] = set()
        self._role_deleted_listener = self._on_role_deleted
        self.role_service = role_service or RoleAggregateService.from_runtime(
            workspace=workspace,
            role_store=role_store,
            session_manager=session_manager,
            # 与启动迁移一致：第一个模型注册即默认模型；桌面端新建/导入的角色默认绑定它。
            default_dialogue_registration_id=(
                registrations[0].id
                if isinstance(registrations, list) and registrations
                else ""
            ),
        )
        self.role_service.add_role_deleted_listener(self._role_deleted_listener)
        self.conversation_service = ConversationService(session_manager)
        self.relationship_runtime = relationship_runtime
        self.presence = presence
        self.scheduler = scheduler
        self.role_tasks = RoleTaskService(
            scheduler=scheduler,
            subagent_manager=subagent_manager,
            memory_optimizer=memory_optimizer,
            session_key_for_role=self.role_service.sessions.derive_session_key,
        )
        self.app_service = DesktopAppService(
            role_service=self.role_service,
            session_manager=session_manager,
            conversation_service=self.conversation_service,
            relationship_runtime=relationship_runtime,
            presence=presence,
        )
        self.session_presenter = DesktopSessionPresenter(
            self.conversation_service,
            relationship_runtime,
        )
        self.role_presenter = DesktopRolePresenter(
            role_store,
            relationship_runtime,
            last_message_for_role=lambda role_id: (
                self.session_presenter.last_message_preview(
                    self.role_service.sessions.derive_session_key(role_id)
                )
            ),
        )
        self.role_card_import_service = (
            card_import_service
            if card_import_service is not None
            else DesktopRoleCardImportService(
                workspace=workspace,
                role_service=self.role_service,
                role_store=role_store,
            )
        )
        self.voice_service = voice_service or VoiceService(
            getattr(config, "voice", None) or VoiceConfig()
        )
        self.chat_service = DesktopChatService(
            agent_loop=agent_loop,
            event_bus=event_bus,
            session_manager=session_manager,
            role_id_from_session_key=self._role_id_from_desktop_session_key,
            sync_desktop_session_thread=self._sync_desktop_session_thread,
            emit_payload=self._emit_event,
            emit_session_updated=self._emit_session_updated,
            tts_service=self.voice_service,
            streaming_enabled=bool(getattr(config, "desktop_streaming_enabled", True)),
        )
        self.voice_handler = DesktopVoiceHandler(
            workspace=workspace,
            voice_service=self.voice_service,
            active_runtime_configs=(
                role.runtime_config
                for role in self.role_service.repository.list_roles()
            ),
            cancel_voice_turn=lambda turn_id: self.chat_service.cancel_voice_turn(
                turn_id
            ),
        )
        self.voice_assets = self.voice_handler.assets
        self.plugin_rpc_registry = plugin_rpc_registry
        self.phone = DesktopPhoneRequestHandler(
            conversations=self.conversation_service,
            accounts=role_store.accounts,
            identities=role_store.identities,
            messages=self.session_presenter,
        )
        self.request_router = DesktopBridgeRequestRouter(
            accounts=DesktopAccountRequestHandler(role_store.accounts),
            identities=DesktopIdentityRequestHandler(role_store.identities),
            phone=self.phone,
            # Needs the runtime's shared group environment; a bare service
            # without one serves no chat info requests.
            phone_memory=(
                DesktopPhoneMemoryRequestHandler(
                    conversations=self.conversation_service,
                    accounts=role_store.accounts,
                    identities=role_store.identities,
                    group_environment=group_environment,
                    members=MemberProfiles(workspace),
                )
                if group_environment is not None
                else None
            ),
            roles=DesktopRoleRequestHandler(
                role_service=self.role_service,
                role_presenter=self.role_presenter,
                voice_handler=self.voice_handler,
                card_import_service=self.role_card_import_service,
                publish_event=self._broadcast_event,
            ),
            sessions_and_tasks=DesktopSessionTaskRequestHandler(
                app_service=self.app_service,
                role_service=self.role_service,
                role_tasks=self.role_tasks,
                session_presenter=self.session_presenter,
                emit_session_updated=self._emit_session_updated,
                emit_tasks_updated=self._emit_role_tasks_updated,
                schedule_task_fields=self._schedule_task_fields,
            ),
            chat=DesktopChatRequestHandler(
                role_service=self.role_service,
                app_service=self.app_service,
                chat_service=self.chat_service,
                start_chat_turn=lambda **kwargs: self._start_chat_turn(**kwargs),
                session_presenter=self.session_presenter,
                sanitize_voice_metrics=_sanitize_voice_metrics,
            ),
            voice=self.voice_handler,
            plugins=DesktopPluginRequestHandler(plugin_rpc_registry),
        )
        if push_tool is not None and activate_transport:
            self.register_desktop_push_channel(push_tool)

    async def _on_turn_committed(self, event: TurnCommitted) -> None:
        """Broadcasts a role turn's committed rows once its shared session is saved.

        External turns refresh the desktop session; rows the turn wrote to the
        role's channel conversations also go to the phone.
        """

        role_id = str(event.role_id or "").strip()
        if not role_id:
            return
        session_key = self.role_service.sessions.derive_session_key(role_id)
        session = self.session_manager.get_or_create(session_key)
        # Only the rows the turn committed; a turn that committed none sends
        # the summary alone.
        messages = committed_turn_messages(session, event) or []
        if event.channel != DESKTOP_CHANNEL:
            request_id = str(event.request_id or "").strip()
            if not request_id:
                request_id = f"turn:{role_id}:{event.thread_id}:{event.timestamp or ''}"
            # Its channel rows are stripped from the desktop timeline, only
            # desktop pushes it made remain.
            await self._broadcast_session_updated(
                request_id=request_id, session=session, messages=messages
            )
        await self._broadcast_phone_updates(role_id, messages)

    async def _on_proactive_message_committed(
        self,
        event: ProactiveMessageCommitted,
    ) -> None:
        """Broadcasts successful proactive commits for desktop and external channels."""

        role_id = str(event.role_id or "").strip()
        if not role_id:
            return
        session_key = self.role_service.sessions.derive_session_key(role_id)
        if event.session_key != session_key:
            return
        # Raised inside a bus observer: EventBus.fanout logs it and carries on,
        # so a malformed event is visible without breaking other listeners.
        if not event.message_id:
            raise ValueError("ProactiveMessageCommitted 缺少 message_id")
        session = self.session_manager.get_or_create(session_key)
        message = next(
            (
                item
                for item in session.messages
                if str(item.get("id") or "") == event.message_id
            ),
            None,
        )
        if message is None:
            # Also logged by EventBus.fanout, like the missing-id error above.
            raise ValueError(f"主动消息不在角色会话中: {event.message_id}")
        await self._broadcast_session_updated(
            request_id=f"proactive:{role_id}",
            session=session,
            messages=[message],
        )
        await self._broadcast_phone_updates(role_id, [message])

    async def _broadcast_phone_updates(
        self, role_id: str, messages: list[dict[str, Any]]
    ) -> None:
        """Sends ``phone.conversation.updated`` for committed channel rows.

        One event per channel conversation among ``messages``, carrying
        exactly those rows and the conversation's refreshed list row; nothing
        when no desktop client listens.
        """
        if not self._event_listeners or not messages:
            return
        for update in self.phone.conversation_updates(role_id, messages):
            await self._broadcast_event(
                BridgeEvent(
                    id=f"phone:{update['thread_id']}",
                    type="event",
                    method=PHONE_CONVERSATION_UPDATED,
                    payload=update,
                ).to_dict()
            )

    def _on_account_change(self, account_id: str) -> None:
        """Pushes ``accounts.updated`` so account views refresh without polling."""
        self._schedule_change_push("accounts.updated", {"account_id": account_id})

    def _on_identity_change(self) -> None:
        """Pushes ``identities.updated`` after a bind, unbind or newly known chat."""
        self._schedule_change_push("identities.updated", {})

    def _schedule_change_push(self, method: str, payload: dict[str, Any]) -> None:
        # Account and identity changes arrive synchronously inside plugin
        # reports or channel intake, often from plugin tasks that inherited an
        # RPC's since-released runtime lease. The push is therefore its own
        # task in a fresh context: it pins no runtime generation and cannot
        # fail the reporting caller; failures are logged by the collector.
        # Unwatched changes are dropped.
        if not self._event_listeners:
            return
        push = self._broadcast_event(
            BridgeEvent(
                id=method, type="event", method=method, payload=payload
            ).to_dict()
        )
        try:
            _ = Context().run(self._change_pushes.spawn, push, name=method)
        except Exception:
            # Bridge boundary: a push that cannot even be scheduled must not
            # surface in the plugin's register/report or intake call.
            push.close()
            logger.exception("Change push %s %r not scheduled", method, payload)

    def add_event_listener(
        self,
        listener: Callable[[dict[str, Any]], Awaitable[None] | None],
    ) -> None:
        self._event_listeners.add(listener)

    def _on_role_deleted(self, role_id: str) -> None:
        clean_role_id = str(role_id or "").strip()
        if not clean_role_id:
            raise ValueError("role_id required for role deletion lifecycle")
        if self.memory_engine is not None:
            invalidate = getattr(self.memory_engine, "invalidate_role_memories", None)
            if not callable(invalidate):
                raise RuntimeError("memory engine lacks role invalidation capability")
            invalidate(clean_role_id)
        self.event_bus.enqueue(RoleDeleted(clean_role_id))

    def remove_event_listener(
        self,
        listener: Callable[[dict[str, Any]], Awaitable[None] | None],
    ) -> None:
        self._event_listeners.discard(listener)

    @property
    def has_event_listeners(self) -> bool:
        """Returns whether an Electron or stream consumer is attached."""

        return bool(self._event_listeners)

    async def publish_event(self, payload: dict[str, Any]) -> None:
        """Publishes one host event to every connected desktop client."""

        await self._broadcast_event(payload)

    def resolve_method_policy(self, method: str) -> MethodPolicy:
        """Resolves dispatcher policy, querying the plugin RPC registry dynamically."""

        return resolve_plugin_method_policy(method, lambda: self.plugin_rpc_registry)

    async def aclose(self) -> None:
        """Releases bridge event subscriptions and desktop chat tasks."""

        self.event_bus.off(TurnCommitted, self._turn_committed_listener)
        self.event_bus.off(
            ProactiveMessageCommitted,
            self._proactive_message_listener,
        )
        self.role_service.remove_role_deleted_listener(self._role_deleted_listener)
        self.role_store.accounts.remove_change_listener(self._account_change_listener)
        self.role_store.identities.remove_change_listener(
            self._identity_change_listener
        )
        self.event_bus.off(PluginBridgeEvent, self._plugin_event_listener)
        self._event_listeners.clear()
        self._change_pushes.cancel_all()
        await self._change_pushes.drain()
        if self.plugin_rpc_registry is not None:
            self.plugin_rpc_registry.communication.retire()
        steps = [
            ("desktop.chat.close", self.chat_service.aclose),
            ("desktop.voice.close", self.voice_handler.aclose),
        ]
        if self.model_resolver is not None and self._owns_model_resolver:
            steps.append(("desktop.models.close", self.model_resolver.aclose))
        await run_cleanup_steps(*steps)

    async def _on_plugin_event(self, event: PluginBridgeEvent) -> None:
        # Retiring and current generations can share a bus; only the owning transport forwards it.
        if (
            event.registry is not self._plugin_event_registry
            or not self._event_listeners
        ):
            return
        await self._broadcast_event(
            {
                "id": event.method,
                "pluginGeneration": (
                    self.plugin_rpc_registry.communication.generation
                    if self.plugin_rpc_registry
                    else ""
                ),
                "type": "event",
                "method": event.method,
                "payload": event.payload,
            }
        )
        event.dispatched = True

    def start_background_tasks(self) -> None:
        """Starts bridge-owned background maintenance after an event loop exists."""

        self.voice_handler.start()

    def register_desktop_push_channel(self, push_tool: MessagePushTool) -> None:
        """Registers the desktop proactive transport against the bridge event stream."""

        async def _emit_session_for_chat(
            chat_id: str,
            *,
            message: str = "",
            media: list[str] | None = None,
            metadata: dict[str, object] | None = None,
        ) -> None:
            if (metadata or {}).get("pending_commit") is True:
                # The turn owner will publish the complete message and state together.
                self.app_service.validate_desktop_push_target(chat_id)
                return
            session_key = self.app_service.normalize_desktop_session_key(chat_id)
            drafts = current_turn_pushes(session_key)
            if (
                drafts is not None
                and metadata is not None
                and metadata.get("already_persisted") is not True
            ):
                self.app_service.validate_desktop_push_target(chat_id)
                drafts.append(
                    self.app_service.build_desktop_push_message(
                        session_key,
                        message=message,
                        media=media,
                        delivery_key=str(metadata.get("delivery_key") or ""),
                    ),
                    owner=self,
                    after_commit=lambda: self.app_service.finish_queued_desktop_push(
                        session_key
                    ),
                )
                metadata["queued"] = True
                return
            session, pushed = await self.app_service.apply_desktop_push(
                chat_id,
                message=message,
                media=media,
                delivery_key=str((metadata or {}).get("delivery_key") or ""),
                already_persisted=(metadata or {}).get("already_persisted") is True,
            )
            await self._broadcast_session_updated(
                request_id="proactive", session=session, messages=[pushed]
            )

        push_tool.register_channel(
            "desktop",
            text_with_metadata=lambda chat_id, message, metadata: _emit_session_for_chat(
                chat_id, message=message, metadata=metadata
            ),
            file=lambda chat_id, file_path, _name=None: _emit_session_for_chat(
                chat_id, media=[file_path]
            ),
            image=lambda chat_id, image_path: _emit_session_for_chat(
                chat_id, media=[image_path]
            ),
            image_with_metadata=lambda chat_id, image_path, metadata: _emit_session_for_chat(
                chat_id, media=[image_path], metadata=metadata
            ),
            description="桌面端，chat_id 使用当前角色会话 ID role:<角色ID>",
        )

    async def _apply_desktop_push(
        self,
        chat_id: str,
        *,
        message: str = "",
        media: list[str] | None = None,
    ) -> Session:
        session, _pushed = await self.app_service.apply_desktop_push(
            chat_id,
            message=message,
            media=media,
        )
        return session

    def _start_chat_turn(
        self,
        *,
        request_id: str,
        turn_id: str,
        session_key: str,
        content: str,
        media: list[str],
        metadata: dict[str, object] | None,
        omit_user_turn: bool,
        emit_event,
    ) -> None:
        self.chat_service.start_chat_turn(
            request_id=request_id,
            turn_id=turn_id,
            session_key=session_key,
            content=content,
            media=media,
            metadata=metadata,
            omit_user_turn=omit_user_turn,
            emit_event=emit_event,
        )

    def _ok(
        self, request_id: str, method: str, payload: dict[str, Any]
    ) -> BridgeResponse:
        return BridgeResponse(
            id=request_id,
            type="response",
            method=method,
            payload=payload,
        )

    def _error(
        self,
        request_id: str,
        method: str,
        code: str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> BridgeResponse:
        return BridgeResponse(
            id=request_id,
            type="response",
            method=method,
            error=BridgeError(code=code, message=message, details=details or {}),
        )

    async def _emit_event(self, emit_event, payload: dict[str, Any]) -> None:
        result = emit_event(payload)
        if inspect.isawaitable(result):
            await result

    async def _broadcast_event(self, payload: dict[str, Any]) -> None:
        listeners = list(self._event_listeners)
        for listener in listeners:
            await self._emit_event(listener, payload)

    async def _emit_session_updated(
        self,
        *,
        request_id: str,
        session: Session,
        emit_event,
        change: str = "message_appended",
        messages: list[dict[str, Any]] | None = None,
    ) -> None:
        """Emits ``session.updated`` carrying exactly ``messages`` (none by default)."""
        event = BridgeEvent(
            id=request_id,
            type="event",
            method="session.updated",
            payload=self._build_session_update_payload(
                session, change=change, messages=messages or []
            ),
        )
        await self._emit_event(emit_event, event.to_dict())

    async def _emit_role_tasks_updated(
        self,
        *,
        request_id: str,
        role_id: str,
        emit_event,
    ) -> None:
        event = BridgeEvent(
            id=request_id,
            type="event",
            method="roles.tasks.updated",
            payload={"role_id": role_id},
        )
        await self._emit_event(emit_event, event.to_dict())

    @staticmethod
    def _schedule_task_fields(payload: dict[str, Any]) -> dict[str, str]:
        return {
            "name": str(payload.get("name") or ""),
            "tier": str(payload.get("tier") or ""),
            "trigger": str(payload.get("trigger") or ""),
            "when": str(payload.get("when") or ""),
            "content": str(payload.get("content") or ""),
        }

    async def _broadcast_session_updated(
        self,
        *,
        request_id: str,
        session: Session,
        change: str = "message_appended",
        messages: list[dict[str, Any]] | None = None,
    ) -> None:
        """Broadcasts ``session.updated`` carrying exactly ``messages``."""
        event = BridgeEvent(
            id=request_id,
            type="event",
            method="session.updated",
            payload=self._build_session_update_payload(
                session, change=change, messages=messages or []
            ),
        )
        await self._broadcast_event(event.to_dict())

    def _build_session_update_payload(
        self,
        session: Session,
        *,
        change: str,
        messages: list[dict[str, Any]],
    ) -> dict[str, Any]:
        # The desktop timeline shows only the desktop conversation: channel
        # turns still refresh the summary but carry none of their messages.
        changed_messages = self.session_presenter.desktop_messages(
            session.key, messages
        )
        primary_message = changed_messages[-1] if changed_messages else None
        return {
            "session": self.session_presenter.serialize_summary(session),
            "change": change,
            "message": (
                self.session_presenter.serialize_message(primary_message)
                if primary_message is not None
                else None
            ),
            "messages": [
                self.session_presenter.serialize_message(message)
                for message in changed_messages
            ],
            "session_key": session.key,
            "role_id": self._role_id_from_desktop_session_key(session.key),
        }

    def _normalize_desktop_session_key(self, chat_id: str) -> str:
        return self.app_service.normalize_desktop_session_key(chat_id)

    def _role_id_from_desktop_session_key(self, session_key: str) -> str:
        return self.app_service.role_id_from_desktop_session_key(session_key)

    def _sync_desktop_session_thread(self, session: Session, *, role_id: str) -> None:
        self.app_service.sync_desktop_session_thread(session, role_id=role_id)

    def _retry_target_has_media(self, payload: dict[str, Any]) -> bool:
        """Whether the user message a `chat.retry` re-runs carries media (picks the vision model)."""
        role_id = str(payload.get("role_id") or "").strip()
        if not role_id:
            return False
        session = self.session_manager.get_or_create(
            self.role_service.sessions.derive_session_key(role_id)
        )
        last = session.messages[-1] if session.messages else None
        return bool(last and last.get("role") == "user" and last.get("media"))

    async def handle(
        self,
        request: dict[str, Any],
        *,
        emit_event,
    ) -> BridgeResponse:
        """Runs one RPC through the domain router and preserves bridge error codes."""

        request_id = str(request.get("id") or "").strip() or "bridge-request"
        method = str(request.get("method") or "").strip()
        raw_payload = request.get("payload")
        payload: dict[str, Any] = raw_payload if isinstance(raw_payload, dict) else {}
        self.start_background_tasks()
        try:
            with ExitStack() as task_scope:
                if (
                    method in {"chat.send", "chat.retry"}
                    and self.model_resolver is not None
                ):
                    has_media = (
                        bool(payload.get("media"))
                        if method == "chat.send"
                        else self._retry_target_has_media(payload)
                    )
                    purpose = "vision" if has_media else "chat"
                    task_scope.enter_context(
                        self.model_resolver.activate(
                            str(payload.get("role_id") or ""),
                            purpose,
                        )
                    )
                result = await self.request_router.dispatch(
                    method,
                    payload,
                    request_id=request_id,
                    emit_event=emit_event,
                )
            if result is not None:
                return self._ok(request_id, method, result)
        except AccountNotFoundError as exc:
            return self._error(
                request_id, method, "account_not_found", f"账号不存在: {exc.args[0]}"
            )
        except KeyError as exc:
            return self._error(request_id, method, "role_not_found", str(exc))
        except VoiceServiceError as exc:
            metrics = getattr(exc, "metrics", None)
            details = {"metrics": metrics.to_dict()} if metrics is not None else {}
            if metrics is not None:
                logger.warning(
                    "voice request failed method=%s provider=%s request_id=%s error_code=%s elapsed_ms=%d audio_duration_ms=%d characters=%d",
                    method,
                    metrics.provider,
                    metrics.request_id,
                    metrics.error_code,
                    metrics.elapsed_ms,
                    metrics.audio_duration_ms,
                    metrics.character_count,
                )
            return self._error(
                request_id,
                method,
                "voice_service_error",
                str(exc),
                details=details,
            )
        except ModelConfigurationError as exc:
            return self._error(
                request_id, method, exc.code, str(exc), details=exc.to_details()
            )
        except ValueError as exc:
            return self._error(request_id, method, "invalid_request", str(exc))
        except ChatTurnBusyError as exc:
            return self._error(request_id, method, "chat_busy", str(exc))
        except PluginRpcError as exc:
            return self._error(request_id, method, exc.code, str(exc))
        except AccountDeletingError as exc:
            # accounts.rules.set/delete while that account is being deleted.
            return self._error(request_id, method, "account_deleting", str(exc))
        except Exception as exc:
            return self._error(request_id, method, "internal_error", str(exc))
        return self._error(
            request_id, method, "unknown_method", f"unknown method: {method}"
        )
