from __future__ import annotations

import asyncio
import inspect
from typing import Any

from agent.looping.core import AgentLoop
from bus.event_bus import EventBus
from bus.events_lifecycle import StreamDeltaReady, TurnCommitted
from core.roles import RoleStore
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
    ) -> None:
        self.workspace = workspace
        self.role_store = role_store
        self.session_manager = session_manager
        self.agent_loop = agent_loop
        self.event_bus = event_bus

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
                    {"roles": [self._serialize_role(role) for role in self.role_store.list_roles()]},
                )
            if method == "roles.create":
                avatar_source = str(payload.get("avatar_source") or "").strip() or None
                raw_illustrations = payload.get("illustration_sources")
                illustration_sources = (
                    [str(item) for item in raw_illustrations if str(item).strip()]
                    if isinstance(raw_illustrations, list)
                    else None
                )
                role = self.role_store.create_role(
                    name=str(payload.get("name") or ""),
                    description=str(payload.get("description") or ""),
                    system_prompt=str(payload.get("system_prompt") or ""),
                    avatar_source=avatar_source,
                    illustration_sources=illustration_sources,
                )
                return self._ok(request_id, method, {"role": self._serialize_role(role)})
            if method == "roles.update":
                avatar_source = str(payload.get("avatar_source") or "").strip() or None
                raw_illustrations = payload.get("illustration_sources")
                illustration_sources = (
                    [str(item) for item in raw_illustrations if str(item).strip()]
                    if isinstance(raw_illustrations, list)
                    else None
                )
                role = self.role_store.update_role(
                    str(payload.get("role_id") or ""),
                    name=payload.get("name"),
                    description=payload.get("description"),
                    system_prompt=payload.get("system_prompt"),
                    avatar_source=avatar_source,
                    clear_avatar=bool(payload.get("clear_avatar")),
                    illustration_sources=illustration_sources,
                    clear_illustrations=bool(payload.get("clear_illustrations")),
                )
                self.session_manager.sync_role_session_metadata(
                    role.id,
                    role_name=role.name,
                    role_prompt=role.system_prompt,
                    valid_illustrations=list(role.illustrations),
                )
                return self._ok(request_id, method, {"role": self._serialize_role(role)})
            if method == "roles.delete":
                role_id = str(payload.get("role_id") or "").strip()
                deleted = self.role_store.delete_role(role_id)
                session_deleted = False
                if deleted:
                    session_deleted = self.session_manager.delete_role_session(role_id)
                return self._ok(
                    request_id,
                    method,
                    {
                        "deleted": deleted,
                        "session_deleted": session_deleted,
                    },
                )
            if method == "session.openByRole":
                role_id = str(payload.get("role_id") or "").strip()
                role = self.role_store.get_role(role_id)
                if role is None:
                    return self._error(request_id, method, "role_not_found", f"role 不存在: {role_id}")
                session = self.session_manager.sync_role_session_metadata(
                    role.id,
                    role_name=role.name,
                    role_prompt=role.system_prompt,
                    valid_illustrations=list(role.illustrations),
                )
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
                role = self.role_store.get_role(role_id)
                if role is None:
                    return self._error(request_id, method, "role_not_found", f"role 不存在: {role_id}")
                active_illustration = payload.get("active_illustration")
                session = self.session_manager.update_role_session_display_state(
                    role.id,
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
                role = self.role_store.get_role(role_id)
                if role is None:
                    return self._error(request_id, method, "role_not_found", f"role 不存在: {role_id}")
                session = self.session_manager.sync_role_session_metadata(
                    role.id,
                    role_name=role.name,
                    role_prompt=role.system_prompt,
                    valid_illustrations=list(role.illustrations),
                )
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
                role = self.role_store.get_role(role_id)
                if role is None:
                    return self._error(request_id, method, "role_not_found", f"role 不存在: {role_id}")
                result = self.agent_loop.request_interrupt(
                    self.session_manager.role_session_key(role.id),
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
            return self._error(request_id, method, "not_found", str(exc))
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
        payload["illustrations_abs"] = [
            str((self.role_store.roles_dir / rel).resolve())
            for rel in illustrations
            if isinstance(rel, str) and rel
        ]
        return payload
