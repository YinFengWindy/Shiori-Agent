from __future__ import annotations

import inspect
import logging
from collections.abc import Awaitable, Callable
from typing import Any, cast

from agent.looping.core import AgentLoop
from agent.tools.message_push import MessagePushTool
from bus.event_bus import EventBus
from bus.events_lifecycle import (
    ProactiveMessageCommitted,
    RoleDeleted,
    TurnCommitted,
)
from conversation.service import ConversationService
from core.integrations.novelai import (
    NovelAIClient,
    NovelAIService,
    NovelAIStore,
    PromptTagStore,
)
from core.integrations.novelai.models import NovelAISettings
from core.net.http import get_default_http_requester
from core.roles import (
    RoleAggregateService,
    RolePetPackageService,
    RoleRelationshipRuntimeService,
    RoleStore,
)
from core.roles.role_runtime import RoleRuntimeRegistry
from core.roles.self_seed import LlmRoleSelfSeedGenerator
from desktop_bridge.app_service import DesktopAppService
from desktop_bridge.chat_requests import DesktopChatRequestHandler
from desktop_bridge.chat_service import ChatTurnBusyError, DesktopChatService
from desktop_bridge.image_requests import DesktopImageRequestHandler
from desktop_bridge.image_service import DesktopImageService
from desktop_bridge.models import BridgeError, BridgeEvent, BridgeResponse
from desktop_bridge.request_router import DesktopBridgeRequestRouter
from desktop_bridge.role_requests import DesktopRoleRequestHandler
from agent.screen_observation.service import ScreenObservationService
from desktop_bridge.role_presenter import DesktopRolePresenter
from desktop_bridge.role_difference_service import RoleDifferenceGenerationService
from desktop_bridge.role_task_service import RoleTaskService
from desktop_bridge.session_task_requests import DesktopSessionTaskRequestHandler
from desktop_bridge.session_presenter import DesktopSessionPresenter
from desktop_bridge.voice.voice_handler import DesktopVoiceHandler
from desktop_bridge.story_simulation_handler import StorySimulationHandler
from story_simulation.errors import StorySimulationError
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
        novelai_service: NovelAIService | None = None,
        novelai_store: NovelAIStore | None = None,
        push_tool: MessagePushTool | None = None,
        relationship_runtime: RoleRelationshipRuntimeService | None = None,
        presence: Any | None = None,
        scheduler: Any | None = None,
        subagent_manager: Any | None = None,
        memory_optimizer: Any | None = None,
        observation_service: ScreenObservationService | None = None,
        voice_service: VoiceService | None = None,
        role_runtime_registry: RoleRuntimeRegistry | None = None,
        story_director: Any | None = None,
        image_tool: Any | None = None,
        memory_engine: Any | None = None,
    ) -> None:
        self.workspace = workspace
        self.role_store = role_store
        self.session_manager = session_manager
        self.agent_loop = agent_loop
        self.event_bus = event_bus
        self._turn_committed_listener = self._on_turn_committed
        self._proactive_message_listener = self._on_proactive_message_committed
        self.event_bus.on(TurnCommitted, self._turn_committed_listener)
        self.event_bus.on(
            ProactiveMessageCommitted,
            self._proactive_message_listener,
        )
        self.config = config
        self.role_runtime_registry = role_runtime_registry
        self.memory_engine = memory_engine
        self._event_listeners: set[
            Callable[[dict[str, Any]], Awaitable[None] | None]
        ] = set()
        self._self_seed_generator = self._build_self_seed_generator()
        self._role_deleted_listener = self._on_role_deleted
        self.role_service = role_service or RoleAggregateService.from_runtime(
            workspace=workspace,
            role_store=role_store,
            session_manager=session_manager,
            self_seed_generator=self._self_seed_generator,
        )
        self.role_service.add_role_deleted_listener(self._role_deleted_listener)
        self.conversation_service = ConversationService(
            session_manager,
            binding_resolver=self.role_service.bindings.resolve_role_id,
        )
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
        self.role_presenter = DesktopRolePresenter(role_store, relationship_runtime)
        self.pet_packages = RolePetPackageService(role_store)
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
        self.novelai_store = novelai_store or NovelAIStore(workspace)
        self.prompt_tag_store = PromptTagStore(workspace)
        self.novelai_service = novelai_service or self._build_novelai_service()
        self.role_difference_service = RoleDifferenceGenerationService(
            role_store=self.role_store,
            novelai_service=self.novelai_service,
            workspace=self.workspace,
        )
        self.image_service = DesktopImageService(
            role_service=self.role_service,
            session_manager=session_manager,
            novelai_service=self.novelai_service,
            novelai_store=self.novelai_store,
            prompt_tag_store=self.prompt_tag_store,
        )
        self.story_simulation = StorySimulationHandler(
            workspace=workspace,
            role_store=role_store,
            director=story_director,
            role_runtime_registry=role_runtime_registry,
            image_tool=image_tool,
        )
        self.observation_service = observation_service
        self.request_router = DesktopBridgeRequestRouter(
            roles=DesktopRoleRequestHandler(
                role_service=self.role_service,
                role_store=role_store,
                pet_packages=self.pet_packages,
                role_differences=self.role_difference_service,
                role_presenter=self.role_presenter,
                voice_handler=self.voice_handler,
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
                agent_loop=agent_loop,
                sanitize_voice_metrics=_sanitize_voice_metrics,
            ),
            images=DesktopImageRequestHandler(
                image_service=self.image_service,
                session_presenter=self.session_presenter,
                emit_session_updated=self._emit_session_updated,
            ),
            voice=self.voice_handler,
            stories=self.story_simulation,
            observation=observation_service,
        )
        if push_tool is not None:
            self.register_desktop_push_channel(push_tool)

    async def _on_turn_committed(self, event: TurnCommitted) -> None:
        """Broadcasts external role turns after their shared session is committed."""

        role_id = str(event.role_id or "").strip()
        if not role_id or event.channel == "desktop":
            return
        session_key = self.role_service.sessions.derive_session_key(role_id)
        session = self.session_manager.get_or_create(session_key)
        request_id = str(event.request_id or "").strip()
        if not request_id:
            request_id = f"turn:{role_id}:{event.thread_id}:{event.timestamp or ''}"
        await self._broadcast_session_updated(
            request_id=request_id,
            session=session,
        )

    async def _on_proactive_message_committed(
        self,
        event: ProactiveMessageCommitted,
    ) -> None:
        """Broadcasts proactive messages delivered through external channels."""

        role_id = str(event.role_id or "").strip()
        if not role_id or event.channel == "desktop":
            return
        session_key = self.role_service.sessions.derive_session_key(role_id)
        if event.session_key != session_key:
            return
        session = self.session_manager.get_or_create(session_key)
        await self._broadcast_session_updated(
            request_id=f"proactive:{role_id}",
            session=session,
        )

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

    async def aclose(self) -> None:
        """Releases bridge event subscriptions and desktop chat tasks."""

        self.event_bus.off(TurnCommitted, self._turn_committed_listener)
        self.event_bus.off(
            ProactiveMessageCommitted,
            self._proactive_message_listener,
        )
        self.role_service.remove_role_deleted_listener(self._role_deleted_listener)
        self._event_listeners.clear()
        await self.chat_service.aclose()
        await self.voice_handler.aclose()
        await self.story_simulation.aclose()

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
        ) -> None:
            session = await self.app_service.apply_desktop_push(
                chat_id,
                message=message,
                media=media,
            )
            await self._broadcast_session_updated(
                request_id="proactive", session=session
            )

        push_tool.register_channel(
            "desktop",
            text=lambda chat_id, message: _emit_session_for_chat(
                chat_id, message=message
            ),
            file=lambda chat_id, file_path, _name=None: _emit_session_for_chat(
                chat_id, media=[file_path]
            ),
            image=lambda chat_id, image_path: _emit_session_for_chat(
                chat_id, media=[image_path]
            ),
        )

    async def _apply_desktop_push(
        self,
        chat_id: str,
        *,
        message: str = "",
        media: list[str] | None = None,
    ) -> Session:
        return await self.app_service.apply_desktop_push(
            chat_id,
            message=message,
            media=media,
        )

    def _start_chat_turn(
        self,
        *,
        request_id: str,
        session_key: str,
        content: str,
        media: list[str],
        metadata: dict[str, object] | None,
        omit_user_turn: bool,
        emit_event,
    ) -> None:
        self.chat_service.start_chat_turn(
            request_id=request_id,
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
    ) -> None:
        event = BridgeEvent(
            id=request_id,
            type="event",
            method="session.updated",
            payload={"session": self.session_presenter.serialize(session)},
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
    ) -> None:
        event = BridgeEvent(
            id=request_id,
            type="event",
            method="session.updated",
            payload={"session": self.session_presenter.serialize(session)},
        )
        await self._broadcast_event(event.to_dict())

    def _normalize_desktop_session_key(self, chat_id: str) -> str:
        return self.app_service.normalize_desktop_session_key(chat_id)

    def _role_id_from_desktop_session_key(self, session_key: str) -> str:
        return self.app_service.role_id_from_desktop_session_key(session_key)

    def _sync_desktop_session_thread(self, session: Session, *, role_id: str) -> None:
        self.app_service.sync_desktop_session_thread(session, role_id=role_id)

    def _build_novelai_service(self) -> NovelAIService | None:
        if self.config is None:
            return None
        settings = cast(
            NovelAISettings,
            getattr(self.config, "novelai", NovelAISettings()),
        )
        return NovelAIService(
            settings=settings,
            client=NovelAIClient(
                get_default_http_requester("external_default"),
                settings,
            ),
            store=self.novelai_store,
            role_store=self.role_store,
            workspace=self.workspace,
        )

    def _build_self_seed_generator(self) -> LlmRoleSelfSeedGenerator | None:
        if self.config is None:
            return None
        try:
            from bootstrap.providers import build_providers

            provider, _light, _agent = build_providers(self.config)
        except Exception:
            return None
        return LlmRoleSelfSeedGenerator(
            provider=provider,
            model=self.config.model,
            role_runtime_registry=self.role_runtime_registry,
        )

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
            result = await self.request_router.dispatch(
                method,
                payload,
                request_id=request_id,
                emit_event=emit_event,
            )
            if result is not None:
                return self._ok(request_id, method, result)
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
        except ValueError as exc:
            return self._error(request_id, method, "invalid_request", str(exc))
        except ChatTurnBusyError as exc:
            return self._error(request_id, method, "chat_busy", str(exc))
        except StorySimulationError as exc:
            return self._error(request_id, method, exc.code, str(exc))
        except Exception as exc:
            return self._error(request_id, method, "internal_error", str(exc))
        return self._error(
            request_id, method, "unknown_method", f"unknown method: {method}"
        )
