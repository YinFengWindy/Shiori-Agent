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
from core.integrations.novelai import NovelAIClient, NovelAIService, NovelAIStore
from core.integrations.novelai.models import GenerateImageRequest, NovelAISettings
from core.net.http import get_default_http_requester
from core.roles import RoleAggregateService, RoleRelationshipRuntimeService, RoleStore
from core.roles.self_seed import LlmRoleSelfSeedGenerator
from desktop_bridge.models import BridgeError, BridgeEvent, BridgeResponse
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
    ) -> None:
        self.workspace = workspace
        self.role_store = role_store
        self.session_manager = session_manager
        self.agent_loop = agent_loop
        self.event_bus = event_bus
        self.config = config
        self._event_listeners: set[Callable[[dict[str, Any]], Awaitable[None] | None]] = set()
        self._chat_tasks: set[asyncio.Task[None]] = set()
        self._self_seed_generator = self._build_self_seed_generator()
        self.role_service = role_service or RoleAggregateService.from_runtime(
            workspace=workspace,
            role_store=role_store,
            session_manager=session_manager,
            self_seed_generator=self._self_seed_generator,
        )
        self.relationship_runtime = relationship_runtime
        self.presence = presence
        self.novelai_store = novelai_store or NovelAIStore(workspace)
        self.novelai_service = novelai_service or self._build_novelai_service()
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
            session = await self._apply_desktop_push(
                chat_id,
                message=message,
                media=media,
            )
            await self._broadcast_session_updated(request_id="proactive", session=session)

        push_tool.register_channel(
            "desktop",
            text=lambda chat_id, message: _emit_session_for_chat(chat_id, message=message),
            file=lambda chat_id, file_path, _name=None: _emit_session_for_chat(chat_id, media=[file_path]),
            image=lambda chat_id, image_path: _emit_session_for_chat(chat_id, media=[image_path]),
        )

    async def _apply_desktop_push(
        self,
        chat_id: str,
        *,
        message: str = "",
        media: list[str] | None = None,
    ) -> Session:
        session_key = self._normalize_desktop_session_key(chat_id)
        session = self.session_manager.get_or_create(session_key)
        normalized_message = str(message or "")
        normalized_media = [item for item in (media or []) if str(item).strip()]
        if self._is_existing_desktop_push(
            session,
            message=normalized_message,
            media=normalized_media,
        ):
            return session
        session.add_message(
            "assistant",
            normalized_message,
            media=normalized_media or None,
            proactive=True,
            tools_used=["message_push"],
        )
        if self.presence is not None:
            self.presence.record_proactive_sent(session.key)
        if self.relationship_runtime is not None:
            self.relationship_runtime.handle_proactive_sent(session.key)
            session.metadata = self.relationship_runtime.enrich_session_metadata(
                dict(session.metadata),
            )
        await self.session_manager.save_async(session)
        return session

    def _is_existing_desktop_push(
        self,
        session: Session,
        *,
        message: str,
        media: list[str],
    ) -> bool:
        if not session.messages:
            return False
        last_message = session.messages[-1]
        if last_message.get("role") != "assistant" or not last_message.get("proactive"):
            return False
        if str(last_message.get("content") or "") != message:
            return False
        last_media = [str(item).strip() for item in list(last_message.get("media") or []) if str(item).strip()]
        return all(item in last_media for item in media)

    def _build_desktop_user_message_metadata(
        self,
        metadata: dict[str, object] | None,
    ) -> dict[str, object]:
        next_metadata = dict(metadata or {})
        next_metadata.pop("persisted_user_content", None)
        next_metadata.setdefault("source", "desktop")
        return next_metadata

    async def _persist_desktop_user_message(
        self,
        *,
        session: Session,
        content: str,
        media: list[str],
        metadata: dict[str, object] | None,
    ) -> Session:
        session.add_message(
            "user",
            content,
            media=media or None,
            metadata=self._build_desktop_user_message_metadata(metadata),
        )
        if self.presence is not None:
            self.presence.record_user_message(session.key)
        if self.relationship_runtime is not None:
            self.relationship_runtime.handle_user_message(session.key)
            session.metadata = self.relationship_runtime.enrich_session_metadata(
                dict(session.metadata),
            )
        await self.session_manager.append_messages(session, session.messages[-1:])
        return session

    async def handle(
        self,
        request: dict[str, Any],
        *,
        emit_event,
    ) -> BridgeResponse:
        request_id = str(request.get("id") or "").strip() or "bridge-request"
        method = str(request.get("method") or "").strip()
        payload = request.get("payload") if isinstance(request.get("payload"), dict) else {}

        try:
            if method == "health":
                return self._ok(request_id, method, {"ok": True})
            if method == "roles.list":
                return self._ok(
                    request_id,
                    method,
                    {"roles": [self._serialize_role(role) for role in self.role_service.repository.list_roles()]},
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
                return self._ok(request_id, method, {"role": self._serialize_role(aggregate.role)})
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
                    [str(item) for item in raw_removed_illustrations if str(item).strip()]
                    if isinstance(raw_removed_illustrations, list)
                    else None
                )
                chat_background = str(payload.get("chat_background") or "").strip() or None
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
                    avatar_source=avatar_source,
                    avatar_asset=avatar_asset,
                    chat_background=chat_background,
                    clear_chat_background=bool(payload.get("clear_chat_background")),
                    clear_avatar=bool(payload.get("clear_avatar")),
                    illustration_sources=illustration_sources,
                    removed_illustrations=removed_illustrations,
                    clear_illustrations=bool(payload.get("clear_illustrations")),
                )
                return self._ok(request_id, method, {"role": self._serialize_role(aggregate.role)})
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
                    return self._error(request_id, method, "invalid_request", "bindings 必须是数组")
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
                aggregate = await self.role_service.open_role_async(role_id)
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
                        "session": self._serialize_session(session),
                    },
                )
            if method == "session.updateDisplayState":
                role_id = str(payload.get("role_id") or "").strip()
                aggregate = await self.role_service.open_role_async(role_id)
                active_illustration = payload.get("active_illustration")
                session = self.role_service.sessions.update_display_state(
                    aggregate.role,
                    active_illustration=str(active_illustration) if active_illustration else None,
                )
                await self._emit_session_updated(
                    request_id=request_id,
                    session=session,
                    emit_event=emit_event,
                )
                return self._ok(
                    request_id,
                    method,
                    {"session": self._serialize_session(session)},
                )
            if method == "chat.send":
                role_id = str(payload.get("role_id") or "").strip()
                content = str(payload.get("content") or "").strip()
                raw_media = payload.get("media")
                media = (
                    [str(item).strip() for item in raw_media if str(item).strip()]
                    if isinstance(raw_media, list)
                    else []
                )
                reply_to_message_id = str(payload.get("reply_to_message_id") or "").strip()
                reply_to_content = str(payload.get("reply_to_content") or "").strip()
                reply_to_sender = str(payload.get("reply_to_sender") or "").strip()
                if not content and not media:
                    return self._error(request_id, method, "invalid_request", "content 和 media 不能同时为空")
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
                        "session": self._serialize_session(session),
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
                if self.novelai_service is None:
                    return self._error(request_id, method, "invalid_request", "NovelAI 未配置")
                role_id = str(payload.get("role_id") or "").strip()
                session_key = str(payload.get("session_key") or "").strip()
                if not session_key and role_id:
                    session_key = self.role_service.sessions.derive_session_key(role_id)
                result = await self.novelai_service.generate(
                    GenerateImageRequest(
                        prompt=str(payload.get("prompt") or ""),
                        mode=str(payload.get("mode") or "txt2img"),  # type: ignore[arg-type]
                        base_image_path=str(payload.get("base_image_path") or ""),
                        strength=(
                            float(payload["strength"])
                            if payload.get("strength") is not None
                            else None
                        ),
                        noise=(
                            float(payload["noise"])
                            if payload.get("noise") is not None
                            else None
                        ),
                        negative_prompt=str(payload.get("negative_prompt") or ""),
                        size_preset=str(payload.get("size_preset") or "square"),  # type: ignore[arg-type]
                        custom_width=(
                            int(payload["custom_width"])
                            if payload.get("custom_width") is not None
                            else None
                        ),
                        custom_height=(
                            int(payload["custom_height"])
                            if payload.get("custom_height") is not None
                            else None
                        ),
                        steps=(
                            int(payload["steps"])
                            if payload.get("steps") is not None
                            else None
                        ),
                        seed=(
                            int(payload["seed"])
                            if payload.get("seed") is not None
                            else None
                        ),
                        sampler=str(payload.get("sampler") or "k_euler"),
                        model=str(payload.get("model") or ""),
                        role_id=role_id,
                        session_key=session_key,
                    )
                )
                return self._ok(
                    request_id,
                    method,
                    {"result": result.to_public_payload()},
                )
            if method == "novelai.history":
                limit = int(payload.get("limit") or 20)
                role_id = str(payload.get("role_id") or "").strip()
                records = self.novelai_store.list_records(limit=limit, role_id=role_id)
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

        return self._error(request_id, method, "unknown_method", f"unknown method: {method}")

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
        collected: list[BridgeEvent] = []

        async def _on_delta(event: StreamDeltaReady) -> None:
            if event.session_key != session_key:
                return
            payload = {
                "session_key": event.session_key,
                "content_delta": event.content_delta,
                "thinking_delta": event.thinking_delta,
            }
            bridge_event = BridgeEvent(
                id=request_id,
                type="event",
                method="chat.delta",
                payload=payload,
            )
            collected.append(bridge_event)
            await self._emit_event(emit_event, bridge_event.to_dict())

        async def _on_done(event: TurnCommitted) -> None:
            if event.session_key != session_key:
                return
            payload = {
                "session_key": event.session_key,
                "reply": event.assistant_response,
                "thinking": event.thinking,
                "tools_used": list(event.tools_used),
            }
            bridge_event = BridgeEvent(
                id=request_id,
                type="event",
                method="chat.done",
                payload=payload,
            )
            collected.append(bridge_event)
            await self._emit_event(emit_event, bridge_event.to_dict())

        self.event_bus.on(StreamDeltaReady, _on_delta)
        self.event_bus.on(TurnCommitted, _on_done)
        try:
            await self.agent_loop.process_direct(
                content,
                session_key=session_key,
                channel="desktop",
                chat_id=session_key,
                omit_user_turn=omit_user_turn,
                media=media,
                metadata=metadata,
                stream_events=True,
            )
            await asyncio.sleep(0)
            session = self.session_manager.get_or_create(session_key)
            await self._emit_session_updated(
                request_id=request_id,
                session=session,
                emit_event=emit_event,
            )
            return session, collected
        except Exception as exc:
            bridge_event = BridgeEvent(
                id=request_id,
                type="event",
                method="chat.error",
                payload={
                    "session_key": session_key,
                    "message": str(exc),
                },
            )
            collected.append(bridge_event)
            await self._emit_event(emit_event, bridge_event.to_dict())
            raise
        finally:
            self.event_bus.off(StreamDeltaReady, _on_delta)
            self.event_bus.off(TurnCommitted, _on_done)

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
        async def _runner() -> None:
            try:
                await self._run_chat_turn(
                    request_id=request_id,
                    session_key=session_key,
                    content=content,
                    media=media,
                    metadata=metadata,
                    omit_user_turn=omit_user_turn,
                    emit_event=emit_event,
                )
            except Exception:
                logger.exception("desktop chat turn failed: %s", session_key)

        task = asyncio.create_task(_runner(), name=f"desktop-chat:{session_key}")
        self._chat_tasks.add(task)
        task.add_done_callback(self._chat_tasks.discard)

    def _ok(self, request_id: str, method: str, payload: dict[str, Any]) -> BridgeResponse:
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

    def _serialize_session(self, session: Session) -> dict[str, Any]:
        def _serialize_message(msg: dict[str, Any]) -> dict[str, Any]:
            metadata = msg.get("metadata")
            merged_metadata = dict(metadata) if isinstance(metadata, dict) else {}
            skip_keys = {
                "id",
                "session_key",
                "seq",
                "role",
                "content",
                "timestamp",
                "reasoning_content",
                "tool_chain",
                "media",
                "metadata",
            }
            for key, value in msg.items():
                if key in skip_keys:
                    continue
                merged_metadata[key] = value
            return {
                "id": msg.get("id"),
                "role": msg.get("role"),
                "content": msg.get("content"),
                "timestamp": msg.get("timestamp"),
                "reasoning_content": msg.get("reasoning_content"),
                "media": list(msg.get("media") or []),
                "metadata": merged_metadata,
            }

        return {
            "key": session.key,
            "created_at": session.created_at.isoformat(),
            "updated_at": session.updated_at.isoformat(),
            "last_consolidated": session.last_consolidated,
            "metadata": self._enrich_session_metadata(dict(session.metadata)),
            "messages": [_serialize_message(msg) for msg in session.messages],
        }

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
            payload={"session": self._serialize_session(session)},
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
            payload={"session": self._serialize_session(session)},
        )
        await self._broadcast_event(event.to_dict())

    def _normalize_desktop_session_key(self, chat_id: str) -> str:
        normalized = str(chat_id or "").strip()
        if normalized.startswith("role:"):
            return normalized
        if normalized:
            return self.role_service.sessions.derive_session_key(normalized)
        raise ValueError("desktop proactive chat_id 不能为空")

    def _serialize_role(self, role) -> dict[str, Any]:
        payload = role.to_dict()
        avatar = payload.get("avatar")
        illustrations = payload.get("illustrations") or []
        payload["avatar_abs"] = (
            str((self.role_store.roles_dir / avatar).resolve())
            if isinstance(avatar, str) and avatar
            else None
        )
        chat_background = payload.get("chat_background")
        payload["chat_background_abs"] = (
            str((self.role_store.roles_dir / chat_background).resolve())
            if isinstance(chat_background, str) and chat_background
            else None
        )
        payload["illustrations_abs"] = [
            str((self.role_store.roles_dir / rel).resolve())
            for rel in illustrations
            if isinstance(rel, str) and rel
        ]
        relationship_runtime = self.relationship_runtime
        if relationship_runtime is not None:
            snapshot = relationship_runtime.read_snapshot(role.id)
            runtime = relationship_runtime.read_loneliness_runtime(role.id)
            if snapshot is not None:
                payload["relationship_snapshot"] = snapshot
            if runtime is not None:
                payload["loneliness_runtime"] = runtime
        return payload

    def _enrich_session_metadata(self, metadata: dict[str, Any]) -> dict[str, Any]:
        relationship_runtime = self.relationship_runtime
        if relationship_runtime is None:
            return metadata
        return relationship_runtime.enrich_session_metadata(metadata)

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
        return LlmRoleSelfSeedGenerator(provider=provider, model=self.config.model)
