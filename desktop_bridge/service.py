from __future__ import annotations

import asyncio
import inspect
from typing import Any

from agent.looping.core import AgentLoop
from bus.event_bus import EventBus
from bus.events_lifecycle import StreamDeltaReady, TurnCommitted
from core.roles import RoleAggregateService, RoleStore
from desktop_bridge.models import BridgeError, BridgeEvent, BridgeResponse
from session.manager import Session, SessionManager


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
    ) -> None:
        self.workspace = workspace
        self.role_store = role_store
        self.session_manager = session_manager
        self.agent_loop = agent_loop
        self.event_bus = event_bus
        self.role_service = role_service or RoleAggregateService.from_runtime(
            workspace=workspace,
            role_store=role_store,
            session_manager=session_manager,
        )

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
                aggregate = self.role_service.create_role(
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
                featured_image = str(payload.get("featured_image") or "").strip() or None
                aggregate = self.role_service.update_role(
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
                    featured_image=featured_image,
                    clear_featured_image=bool(payload.get("clear_featured_image")),
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
                aggregate = self.role_service.open_role(role_id)
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
                aggregate = self.role_service.open_role(role_id)
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
                if not content:
                    return self._error(request_id, method, "invalid_request", "content 不能为空")
                aggregate = self.role_service.open_role(role_id)
                session = aggregate.session
                session, events = await self._run_chat_turn(
                    request_id=request_id,
                    session_key=session.key,
                    content=content,
                    emit_event=emit_event,
                )
                return self._ok(
                    request_id,
                    method,
                    {
                        "session": self._serialize_session(session),
                        "events": [event.to_dict() for event in events],
                    },
                )
            if method == "chat.cancel":
                role_id = str(payload.get("role_id") or "").strip()
                aggregate = self.role_service.open_role(role_id)
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
        return {
            "key": session.key,
            "created_at": session.created_at.isoformat(),
            "updated_at": session.updated_at.isoformat(),
            "last_consolidated": session.last_consolidated,
            "metadata": dict(session.metadata),
            "messages": [
                {
                    "id": msg.get("id"),
                    "role": msg.get("role"),
                    "content": msg.get("content"),
                    "timestamp": msg.get("timestamp"),
                    "reasoning_content": msg.get("reasoning_content"),
                    "media": list(msg.get("media") or []),
                    "metadata": dict(msg.get("metadata") or {}),
                }
                for msg in session.messages
            ],
        }

    async def _emit_event(self, emit_event, payload: dict[str, Any]) -> None:
        result = emit_event(payload)
        if inspect.isawaitable(result):
            await result

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

    def _serialize_role(self, role) -> dict[str, Any]:
        payload = role.to_dict()
        avatar = payload.get("avatar")
        illustrations = payload.get("illustrations") or []
        payload["avatar_abs"] = (
            str((self.role_store.roles_dir / avatar).resolve())
            if isinstance(avatar, str) and avatar
            else None
        )
        featured_image = payload.get("featured_image")
        payload["featured_image_abs"] = (
            str((self.role_store.roles_dir / featured_image).resolve())
            if isinstance(featured_image, str) and featured_image
            else None
        )
        payload["illustrations_abs"] = [
            str((self.role_store.roles_dir / rel).resolve())
            for rel in illustrations
            if isinstance(rel, str) and rel
        ]
        return payload
