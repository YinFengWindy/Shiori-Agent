from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from core.roles import RoleAggregateService
from session.manager import Session

from .app_service import DesktopAppService
from .role_task_service import RoleTaskService
from .session_presenter import DesktopSessionPresenter

EventEmitter = Callable[[dict[str, Any]], Awaitable[None] | None]
EmitSessionUpdated = Callable[..., Awaitable[None]]
EmitTasksUpdated = Callable[..., Awaitable[None]]


class DesktopSessionTaskRequestHandler:
    """Handles session presentation and role task bridge requests."""

    def __init__(
        self,
        *,
        app_service: DesktopAppService,
        role_service: RoleAggregateService,
        role_tasks: RoleTaskService,
        session_presenter: DesktopSessionPresenter,
        emit_session_updated: EmitSessionUpdated,
        emit_tasks_updated: EmitTasksUpdated,
        schedule_task_fields: Callable[[dict[str, Any]], dict[str, str]],
    ) -> None:
        self._app_service = app_service
        self._role_service = role_service
        self._role_tasks = role_tasks
        self._session_presenter = session_presenter
        self._emit_session_updated = emit_session_updated
        self._emit_tasks_updated = emit_tasks_updated
        self._schedule_task_fields = schedule_task_fields

    async def handle(
        self,
        method: str,
        payload: dict[str, Any],
        *,
        request_id: str,
        emit_event: EventEmitter,
    ) -> dict[str, Any] | None:
        if method == "session.openByRole":
            aggregate = await self._app_service.open_role_session(
                str(payload.get("role_id") or "").strip()
            )
            return await self._session_payload(
                request_id=request_id,
                session=aggregate.session,
                emit_event=emit_event,
            )
        if method == "session.messagesPage":
            session_key = self._desktop_session_key(payload, required=True)
            assert session_key is not None
            meta = self._app_service.session_manager._store.get_session_meta(session_key)
            if meta is None:
                session = Session(key=session_key)
            else:
                session = Session(
                    key=session_key,
                    created_at=datetime.fromisoformat(meta["created_at"]),
                    updated_at=datetime.fromisoformat(meta["updated_at"]),
                    metadata=dict(meta.get("metadata") or {}),
                    last_consolidated=int(meta.get("last_consolidated", 0) or 0),
                )
            before_seq = payload.get("before_seq")
            parsed_before = int(before_seq) if before_seq is not None else None
            return {
                "session": self._session_presenter.serialize_summary(session),
                "page": self._session_presenter.serialize_page(
                    session,
                    before_seq=parsed_before,
                    limit=int(payload.get("limit") or 50),
                ),
            }
        if method == "session.messagesAround":
            message_id = str(payload.get("message_id") or "").strip()
            if not message_id:
                raise ValueError("message_id 不能为空")
            requested_session_key = self._desktop_session_key(payload, required=False)
            raw_context = payload.get("context")
            around = self._session_presenter.serialize_around(
                message_id,
                context=5 if raw_context is None else int(raw_context),
            )
            if not around.get("messages"):
                raise ValueError(f"消息不存在: {message_id}")
            session_key = str(around.get("session_key") or "")
            if requested_session_key and requested_session_key != session_key:
                raise ValueError("message_id 不属于指定会话")
            return {
                "around": around,
                "role_id": self._app_service.role_id_from_desktop_session_key(
                    session_key
                ),
            }
        if method == "session.search":
            query = str(payload.get("query") or "").strip()
            if not query:
                raise ValueError("query 不能为空")
            session_key = self._desktop_session_key(payload, required=False)
            return self._session_presenter.serialize_search(
                query,
                session_key=session_key,
                role=payload.get("role"),
                limit=int(payload.get("limit") or 20),
                offset=int(payload.get("offset") or 0),
            )
        if method == "session.imageHistory":
            session_key = self._desktop_session_key(payload, required=True)
            assert session_key is not None
            return self._session_presenter.serialize_image_history(session_key)
        if method == "session.updateDisplayState":
            active_illustration = payload.get("active_illustration")
            session = await self._app_service.update_display_state(
                str(payload.get("role_id") or "").strip(),
                active_illustration=(
                    str(active_illustration) if active_illustration else None
                ),
            )
            return await self._session_payload(
                request_id=request_id,
                session=session,
                emit_event=emit_event,
            )
        if method == "roles.tasks.list":
            role_id = self._role_id(payload)
            self._role_service.repository.get_required(role_id)
            return {"tasks": self._role_tasks.list_tasks(role_id)}
        if method == "roles.tasks.create":
            role_id = self._role_id(payload)
            self._role_service.repository.get_required(role_id)
            task = self._role_tasks.create_schedule_task(
                role_id,
                **self._schedule_task_fields(payload),
            )
            await self._emit_tasks_updated(
                request_id=request_id,
                role_id=role_id,
                emit_event=emit_event,
            )
            return {"task": task}
        if method == "roles.tasks.update":
            role_id = self._role_id(payload)
            task_id = str(payload.get("task_id") or "").strip()
            self._role_service.repository.get_required(role_id)
            if not task_id:
                raise ValueError("task_id 不能为空")
            task = self._role_tasks.update_schedule_task(
                role_id,
                task_id,
                **self._schedule_task_fields(payload),
            )
            await self._emit_tasks_updated(
                request_id=request_id,
                role_id=role_id,
                emit_event=emit_event,
            )
            return {"task": task}
        if method == "roles.tasks.cancel":
            role_id = self._role_id(payload)
            task_id = str(payload.get("task_id") or "").strip()
            self._role_service.repository.get_required(role_id)
            if not task_id:
                raise ValueError("task_id 不能为空")
            tasks = await self._role_tasks.cancel_task(role_id, task_id)
            await self._emit_tasks_updated(
                request_id=request_id,
                role_id=role_id,
                emit_event=emit_event,
            )
            return {"tasks": tasks}
        return None

    async def _session_payload(
        self,
        *,
        request_id: str,
        session: Session,
        emit_event: EventEmitter,
    ) -> dict[str, Any]:
        await self._emit_session_updated(
            request_id=request_id,
            session=session,
            emit_event=emit_event,
            change="metadata_updated",
            include_message=False,
        )
        return {
            "session": self._session_presenter.serialize_summary(session),
            "page": self._session_presenter.serialize_page(session),
        }

    @staticmethod
    def _role_id(payload: dict[str, Any]) -> str:
        return str(payload.get("role_id") or "").strip()

    def _desktop_session_key(
        self,
        payload: dict[str, Any],
        *,
        required: bool,
    ) -> str | None:
        role_id = str(payload.get("role_id") or "").strip()
        session_key = str(payload.get("session_key") or "").strip()
        if not role_id and not session_key:
            if required:
                raise ValueError("role_id 或 session_key 至少提供一个")
            return None
        if role_id:
            self._role_service.repository.get_required(role_id)
            expected_session_key = self._role_service.sessions.derive_session_key(role_id)
            if session_key and session_key != expected_session_key:
                raise ValueError("role_id 与 session_key 不匹配")
            return expected_session_key

        derived_role_id = self._app_service.role_id_from_desktop_session_key(session_key)
        if not derived_role_id:
            raise ValueError("session_key 不是桌面角色会话")
        self._role_service.repository.get_required(derived_role_id)
        return session_key
