from __future__ import annotations

from collections.abc import Awaitable, Callable
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
        )
        return {"session": self._session_presenter.serialize(session)}

    @staticmethod
    def _role_id(payload: dict[str, Any]) -> str:
        return str(payload.get("role_id") or "").strip()
