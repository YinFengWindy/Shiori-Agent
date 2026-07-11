from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Awaitable, Callable
from typing import Any, cast

from agent.looping.core import AgentLoop
from agent.tools.message_push import MessagePushTool
from bus.event_bus import EventBus
from bus.events_lifecycle import StreamDeltaReady, TurnCommitted
from conversation.service import ConversationService
from core.integrations.novelai import NovelAIClient, NovelAIService, NovelAIStore
from core.integrations.novelai.models import NovelAISettings
from core.net.http import get_default_http_requester
from core.roles import RoleAggregateService, RoleRelationshipRuntimeService, RoleStore
from core.roles.self_seed import LlmRoleSelfSeedGenerator
from desktop_bridge.app_service import DesktopAppService
from desktop_bridge.chat_service import DesktopChatService
from desktop_bridge.image_service import DesktopImageService
from desktop_bridge.models import BridgeError, BridgeEvent, BridgeResponse
from desktop_bridge.role_presenter import DesktopRolePresenter
from desktop_bridge.session_presenter import DesktopSessionPresenter
from infra.channels.reply_context import build_inbound_text_with_reply_context
from session.manager import Session, SessionManager

logger = logging.getLogger("desktop.bridge")


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
    ) -> None:
        self.workspace = workspace
        self.role_store = role_store
        self.session_manager = session_manager
        self.agent_loop = agent_loop
        self.event_bus = event_bus
        self.config = config
        self._event_listeners: set[
            Callable[[dict[str, Any]], Awaitable[None] | None]
        ] = set()
        self._self_seed_generator = self._build_self_seed_generator()
        self.role_service = role_service or RoleAggregateService.from_runtime(
            workspace=workspace,
            role_store=role_store,
            session_manager=session_manager,
            self_seed_generator=self._self_seed_generator,
        )
        self.conversation_service = ConversationService(
            session_manager,
            binding_resolver=self.role_service.bindings.resolve_role_id,
        )
        self.relationship_runtime = relationship_runtime
        self.presence = presence
        self.scheduler = scheduler
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
        self.chat_service = DesktopChatService(
            agent_loop=agent_loop,
            event_bus=event_bus,
            session_manager=session_manager,
            role_id_from_session_key=self._role_id_from_desktop_session_key,
            sync_desktop_session_thread=self._sync_desktop_session_thread,
            emit_payload=self._emit_event,
            emit_session_updated=self._emit_session_updated,
        )
        self.novelai_store = novelai_store or NovelAIStore(workspace)
        self.novelai_service = novelai_service or self._build_novelai_service()
        self.image_service = DesktopImageService(
            role_service=self.role_service,
            novelai_service=self.novelai_service,
            novelai_store=self.novelai_store,
        )
        if push_tool is not None:
            self.register_desktop_push_channel(push_tool)

    def add_event_listener(
        self,
        listener: Callable[[dict[str, Any]], Awaitable[None] | None],
    ) -> None:
        self._event_listeners.add(listener)

    def remove_event_listener(
        self,
        listener: Callable[[dict[str, Any]], Awaitable[None] | None],
    ) -> None:
        self._event_listeners.discard(listener)

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

    def _build_desktop_user_message_metadata(
        self,
        metadata: dict[str, object] | None,
    ) -> dict[str, object]:
        return self.app_service.build_desktop_user_message_metadata(metadata)

    async def _persist_desktop_user_message(
        self,
        *,
        session: Session,
        role_id: str,
        content: str,
        media: list[str],
        metadata: dict[str, object] | None,
    ) -> Session:
        return await self.app_service.persist_desktop_user_message(
            session=session,
            role_id=role_id,
            content=content,
            media=media,
            metadata=metadata,
        )

    async def handle(
        self,
        request: dict[str, Any],
        *,
        emit_event,
    ) -> BridgeResponse:
        request_id = str(request.get("id") or "").strip() or "bridge-request"
        method = str(request.get("method") or "").strip()
        payload = (
            request.get("payload") if isinstance(request.get("payload"), dict) else {}
        )

        try:
            if method == "health":
                return self._ok(request_id, method, {"ok": True})
            if method == "roles.list":
                return self._ok(
                    request_id,
                    method,
                    {
                        "roles": [
                            self.role_presenter.serialize(role)
                            for role in self.role_service.repository.list_roles()
                        ]
                    },
                )
            if method == "roles.create":
                avatar_source = str(payload.get("avatar_source") or "").strip() or None
                raw_illustrations = payload.get("illustration_sources")
                illustration_sources = (
                    [str(item) for item in raw_illustrations if str(item).strip()]
                    if isinstance(raw_illustrations, list)
                    else None
                )
                aggregate = await self.role_service.create_role_async(
                    role_id=str(payload.get("role_id") or "").strip() or None,
                    name=str(payload.get("name") or ""),
                    description=str(payload.get("description") or ""),
                    system_prompt=str(payload.get("system_prompt") or ""),
                    background=str(payload.get("background") or ""),
                    runtime_config=(
                        dict(payload.get("runtime_config"))
                        if isinstance(payload.get("runtime_config"), dict)
                        else None
                    ),
                    avatar_source=avatar_source,
                    illustration_sources=illustration_sources,
                )
                return self._ok(
                    request_id, method, {"role": self.role_presenter.serialize(aggregate.role)}
                )
            if method == "roles.update":
                avatar_source = str(payload.get("avatar_source") or "").strip() or None
                avatar_asset = str(payload.get("avatar_asset") or "").strip() or None
                raw_illustrations = payload.get("illustration_sources")
                illustration_sources = (
                    [str(item) for item in raw_illustrations if str(item).strip()]
                    if isinstance(raw_illustrations, list)
                    else None
                )
                raw_removed_illustrations = payload.get("removed_illustrations")
                removed_illustrations = (
                    [
                        str(item)
                        for item in raw_removed_illustrations
                        if str(item).strip()
                    ]
                    if isinstance(raw_removed_illustrations, list)
                    else None
                )
                chat_background = (
                    str(payload.get("chat_background") or "").strip() or None
                )
                aggregate = await self.role_service.update_role_async(
                    str(payload.get("role_id") or ""),
                    name=payload.get("name"),
                    description=payload.get("description"),
                    system_prompt=payload.get("system_prompt"),
                    background=payload.get("background"),
                    runtime_config=(
                        dict(payload.get("runtime_config"))
                        if isinstance(payload.get("runtime_config"), dict)
                        else None
                    ),
                    channel_bindings=(
                        list(payload.get("channel_bindings"))
                        if isinstance(payload.get("channel_bindings"), list)
                        else None
                    ),
                    proactive=(
                        dict(payload.get("proactive"))
                        if isinstance(payload.get("proactive"), dict)
                        else None
                    ),
                    avatar_source=avatar_source,
                    avatar_asset=avatar_asset,
                    chat_background=chat_background,
                    clear_chat_background=bool(payload.get("clear_chat_background")),
                    clear_avatar=bool(payload.get("clear_avatar")),
                    illustration_sources=illustration_sources,
                    removed_illustrations=removed_illustrations,
                    clear_illustrations=bool(payload.get("clear_illustrations")),
                )
                return self._ok(
                    request_id, method, {"role": self.role_presenter.serialize(aggregate.role)}
                )
            if method == "roles.delete":
                role_id = str(payload.get("role_id") or "").strip()
                deleted, session_deleted = self.role_service.delete_role(role_id)
                return self._ok(
                    request_id,
                    method,
                    {
                        "deleted": deleted,
                        "session_deleted": session_deleted,
                    },
                )
            if method == "roles.bindings.list":
                return self._ok(
                    request_id,
                    method,
                    {
                        "bindings": [
                            binding.to_dict()
                            for binding in self.role_service.bindings.list_bindings()
                        ],
                    },
                )
            if method == "roles.bindings.replace":
                raw_bindings = payload.get("bindings")
                if not isinstance(raw_bindings, list):
                    return self._error(
                        request_id, method, "invalid_request", "bindings 必须是数组"
                    )
                bindings = self.role_service.bindings.replace_bindings(
                    [
                        {
                            "channel": str(item.get("channel") or ""),
                            "chat_id": str(item.get("chat_id") or ""),
                            "role_id": str(item.get("role_id") or ""),
                        }
                        for item in raw_bindings
                        if isinstance(item, dict)
                    ]
                )
                return self._ok(
                    request_id,
                    method,
                    {
                        "bindings": [binding.to_dict() for binding in bindings],
                    },
                )
            if method == "session.openByRole":
                role_id = str(payload.get("role_id") or "").strip()
                aggregate = await self.app_service.open_role_session(role_id)
                session = aggregate.session
                await self._emit_session_updated(
                    request_id=request_id,
                    session=session,
                    emit_event=emit_event,
                )
                return self._ok(
                    request_id,
                    method,
                    {
                        "session": self.session_presenter.serialize(session),
                    },
                )
            if method == "session.updateDisplayState":
                role_id = str(payload.get("role_id") or "").strip()
                active_illustration = payload.get("active_illustration")
                session = await self.app_service.update_display_state(
                    role_id,
                    active_illustration=(
                        str(active_illustration) if active_illustration else None
                    ),
                )
                await self._emit_session_updated(
                    request_id=request_id,
                    session=session,
                    emit_event=emit_event,
                )
                return self._ok(
                    request_id,
                    method,
                    {"session": self.session_presenter.serialize(session)},
                )
            if method == "roles.tasks.list":
                role_id = str(payload.get("role_id") or "").strip()
                self.role_service.repository.get_required(role_id)
                return self._ok(
                    request_id,
                    method,
                    {"tasks": self._list_role_tasks(role_id)},
                )
            if method == "roles.tasks.cancel":
                role_id = str(payload.get("role_id") or "").strip()
                task_id = str(payload.get("task_id") or "").strip()
                self.role_service.repository.get_required(role_id)
                if not task_id:
                    raise ValueError("task_id 不能为空")
                if self.scheduler is None:
                    raise RuntimeError("调度器未启用")
                job = next((item for item in self.scheduler.list_jobs() if item.id == task_id), None)
                if job is None or job.role_id != role_id:
                    raise KeyError("角色任务不存在")
                if not self.scheduler.cancel_job(task_id):
                    raise RuntimeError("取消任务失败")
                return self._ok(request_id, method, {"tasks": self._list_role_tasks(role_id)})
            if method == "chat.send":
                role_id = str(payload.get("role_id") or "").strip()
                content = str(payload.get("content") or "").strip()
                raw_media = payload.get("media")
                media = (
                    [str(item).strip() for item in raw_media if str(item).strip()]
                    if isinstance(raw_media, list)
                    else []
                )
                reply_to_message_id = str(
                    payload.get("reply_to_message_id") or ""
                ).strip()
                reply_to_content = str(payload.get("reply_to_content") or "").strip()
                reply_to_sender = str(payload.get("reply_to_sender") or "").strip()
                if not content and not media:
                    return self._error(
                        request_id,
                        method,
                        "invalid_request",
                        "content 和 media 不能同时为空",
                    )
                aggregate = await self.role_service.open_role_async(role_id)
                session = aggregate.session
                inbound_content = content
                persisted_user_content = content
                metadata: dict[str, object] = {}
                if reply_to_message_id:
                    metadata["reply_to_message_id"] = reply_to_message_id
                if reply_to_sender:
                    metadata["reply_to_sender"] = reply_to_sender
                if reply_to_content:
                    metadata["reply_to_content"] = reply_to_content
                    metadata["persisted_user_content"] = content
                    inbound_content = build_inbound_text_with_reply_context(
                        user_text=content,
                        reply_text=reply_to_content,
                        reply_sender=reply_to_sender,
                    )
                await self._persist_desktop_user_message(
                    session=session,
                    role_id=aggregate.role.id,
                    content=persisted_user_content,
                    media=media,
                    metadata=metadata,
                )
                self._start_chat_turn(
                    request_id=request_id,
                    session_key=session.key,
                    content=inbound_content,
                    media=media,
                    metadata=metadata,
                    omit_user_turn=True,
                    emit_event=emit_event,
                )
                return self._ok(
                    request_id,
                    method,
                    {
                        "session": self.session_presenter.serialize(session),
                        "events": [],
                    },
                )
            if method == "chat.cancel":
                role_id = str(payload.get("role_id") or "").strip()
                aggregate = await self.role_service.open_role_async(role_id)
                result = self.agent_loop.request_interrupt(
                    self.role_service.sessions.derive_session_key(aggregate.role.id),
                    sender="desktop",
                    command="/cancel",
                )
                return self._ok(
                    request_id,
                    method,
                    {
                        "status": result.status,
                        "message": result.message,
                        "session_key": result.session_key,
                    },
                )
            if method == "novelai.generate":
                result = await self.image_service.generate(payload)
                return self._ok(
                    request_id,
                    method,
                    {"result": result},
                )
            if method == "novelai.history":
                records = self.image_service.history(payload)
                return self._ok(
                    request_id,
                    method,
                    {"records": records},
                )
        except KeyError as exc:
            return self._error(request_id, method, "role_not_found", str(exc))
        except ValueError as exc:
            return self._error(request_id, method, "invalid_request", str(exc))
        except Exception as exc:
            return self._error(request_id, method, "internal_error", str(exc))

        return self._error(
            request_id, method, "unknown_method", f"unknown method: {method}"
        )

    async def _run_chat_turn(
        self,
        *,
        request_id: str,
        session_key: str,
        content: str,
        media: list[str],
        metadata: dict[str, object] | None,
        omit_user_turn: bool,
        emit_event,
    ) -> tuple[Session, list[BridgeEvent]]:
        return await self.chat_service.run_chat_turn(
            request_id=request_id,
            session_key=session_key,
            content=content,
            media=media,
            metadata=metadata,
            omit_user_turn=omit_user_turn,
            emit_event=emit_event,
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
    ) -> BridgeResponse:
        return BridgeResponse(
            id=request_id,
            type="response",
            method=method,
            error=BridgeError(code=code, message=message),
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

    def _list_role_tasks(self, role_id: str) -> list[dict[str, object]]:
        schedule_tasks = [] if self.scheduler is None else [
            {
                "id": job.id,
                "role_id": job.role_id,
                "kind": "schedule",
                "status": "running" if job.id in self.scheduler._active_tasks else "scheduled",
                "label": job.name or job.id[:8],
                "detail": job.message or job.prompt or "",
                "created_at": job.created_at.isoformat(),
                "next_run_at": job.fire_at.isoformat(),
                "cancellable": True,
            }
            for job in self.scheduler.list_jobs()
            if job.role_id == role_id
        ]
        spawn_tool = self.agent_loop.tools.get_tool("spawn")
        manager = getattr(spawn_tool, "_manager", None)
        if manager is None:
            return schedule_tasks
        role_session_key = self.role_service.sessions.derive_session_key(role_id)
        subagent_tasks = [
            {
                "id": str(job["job_id"]),
                "role_id": role_id,
                "kind": "subagent",
                "status": "running",
                "label": str(job["label"]),
                "detail": str(job["task"]),
                "created_at": str(job["started_at"]),
                "next_run_at": "",
                "cancellable": True,
            }
            for job in manager.list_running_jobs()
            if str(job.get("origin_chat_id") or "") == role_session_key
        ]
        return [*schedule_tasks, *subagent_tasks]

    def _build_self_seed_generator(self) -> LlmRoleSelfSeedGenerator | None:
        if self.config is None:
            return None
        try:
            from bootstrap.providers import build_providers

            provider, _light, _agent = build_providers(self.config)
        except Exception:
            return None
        return LlmRoleSelfSeedGenerator(provider=provider, model=self.config.model)
