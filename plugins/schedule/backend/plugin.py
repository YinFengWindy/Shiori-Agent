"""Schedule: role jobs that fire at set times, their tools and the task block.

The scheduler is a process resource: one per process, loaded and ticking
from the first setup until the plugin is disabled or the process exits.
Every generation's setup only rebinds the host port, the tools, the RPC and
the event subscription to it.
"""

from __future__ import annotations

from shiori_sdk.core.schedule_host import SCHEDULE_HOST
from shiori_sdk.core.scheduler import (
    SCHEDULER,
    ScheduledJobInfo,
    ScheduleRequest,
)
from shiori_sdk.core.services import (
    BACKGROUND,
    EVENTS,
    PROCESS_RESOURCES,
    ROLES,
    RPC,
    TOOLS,
    WORKSPACE,
)
from shiori_sdk.role_events import RoleDeleted
from shiori_sdk.roles import Roles
from shiori_sdk.rpc import Concurrency
from shiori_sdk.runtime import PluginRuntimeContext

from .presenter import job_info, serialize_task
from .scheduler import DEFAULT_SCHEDULE_TIMEZONE, LatencyTracker, SchedulerService
from .tools import CancelScheduleTool, ListSchedulesTool, ScheduleTool

# Versioned process-resource contract; bump it when the retained object's
# methods change incompatibly, so a reload builds a fresh scheduler.
_RESOURCE_KEY = "scheduler-v1"
# Renderer event after a role's jobs changed or ran
# (``plugin.schedule.tasks.changed``, payload ``{role_id}``).
TASKS_CHANGED_EVENT = "tasks.changed"


class SchedulerPort:
    """``SCHEDULER`` over the process-wide scheduler."""

    def __init__(self, service: SchedulerService) -> None:
        self._service = service

    def create_job(self, request: ScheduleRequest) -> ScheduledJobInfo:
        job = self._service.create_job(
            name=request.name,
            tier=request.tier,
            trigger=request.trigger,
            when=request.when,
            content=request.content,
            timezone_name=request.timezone,
            channel=request.channel,
            chat_id=request.chat_id,
            role_id=request.role_id,
            thread_id=request.thread_id,
        )
        return job_info(job, running=False)

    def list_jobs(self, role_id: str) -> list[ScheduledJobInfo]:
        return [
            job_info(job, running=self._service.is_job_active(job.id))
            for job in self._service.list_jobs()
            if job.role_id == role_id
        ]

    def cancel_job(self, role_id: str, job_id: str) -> bool:
        return self._service.cancel_role_job(role_id, job_id)


class ScheduleApi:
    """Plugin RPC the role task block calls; every job is bound to the desktop chat."""

    def __init__(self, service: SchedulerService, roles: Roles) -> None:
        self._service = service
        self._roles = roles

    async def list_tasks(self, payload: dict[str, object]) -> dict[str, object]:
        """The role's jobs, oldest first."""
        role_id = self._role_id(payload)
        return {"tasks": self._tasks(role_id)}

    async def create(self, payload: dict[str, object]) -> dict[str, object]:
        """A new job delivered to the role's desktop chat."""
        role_id = self._role_id(payload)
        job = self._service.create_job(
            **_form_fields(payload),
            # The desktop chat of a role is its shared session.
            channel="desktop",
            chat_id=f"role:{role_id}",
            role_id=role_id,
        )
        return {"task": serialize_task(job, running=False)}

    async def update(self, payload: dict[str, object]) -> dict[str, object]:
        """Replaces an idle job of the role."""
        role_id = self._role_id(payload)
        job = self._service.update_job(
            _task_id(payload), role_id=role_id, **_form_fields(payload)
        )
        return {"task": serialize_task(job, running=False)}

    async def cancel(self, payload: dict[str, object]) -> dict[str, object]:
        """Removes the role's job, stopping it if it runs."""
        role_id = self._role_id(payload)
        if not self._service.cancel_role_job(role_id, _task_id(payload)):
            raise KeyError("角色任务不存在")
        return {"tasks": self._tasks(role_id)}

    def _role_id(self, payload: dict[str, object]) -> str:
        role_id = str(payload.get("role_id") or "").strip()
        if self._roles.get_role(role_id) is None:
            raise ValueError(f"role not found: {role_id}")
        return role_id

    def _tasks(self, role_id: str) -> list[dict[str, object]]:
        jobs = sorted(
            (job for job in self._service.list_jobs() if job.role_id == role_id),
            key=lambda job: (job.created_at, job.id),
        )
        return [
            serialize_task(job, running=self._service.is_job_active(job.id))
            for job in jobs
        ]


def _task_id(payload: dict[str, object]) -> str:
    task_id = str(payload.get("task_id") or "").strip()
    if not task_id:
        raise ValueError("task_id 不能为空")
    return task_id


def _form_fields(payload: dict[str, object]) -> dict[str, str]:
    """The fields the task form edits; desktop jobs use the default timezone."""
    return {
        "name": str(payload.get("name") or ""),
        "tier": str(payload.get("tier") or ""),
        "trigger": str(payload.get("trigger") or ""),
        "when": str(payload.get("when") or ""),
        "content": str(payload.get("content") or ""),
        "timezone_name": DEFAULT_SCHEDULE_TIMEZONE,
    }


async def setup(ctx: PluginRuntimeContext) -> None:
    """Attaches to the process scheduler and serves its tools, RPC and key."""
    resources = ctx.require(PROCESS_RESOURCES)
    store_path = ctx.require(WORKSPACE) / "schedules.json"
    service = resources.acquire(
        _RESOURCE_KEY, lambda: SchedulerService(store_path, tracker=LatencyTracker())
    )
    roles = ctx.require(ROLES)
    # Only the first setup of the process loads the store and starts ticking.
    service.start(
        ctx.require(SCHEDULE_HOST),
        role_exists=lambda role_id: roles.get_role(role_id) is not None,
    )

    async def role_deleted(event: RoleDeleted) -> None:
        service.cancel_role_jobs(event.role_id)

    ctx.require(EVENTS).on(RoleDeleted, role_deleted)

    tools = ctx.require(TOOLS)
    tools.register(
        ScheduleTool(service), risk="write", search_hint="cron timer 延时执行"
    )
    tools.register(
        ListSchedulesTool(service),
        risk="read-only",
        search_hint="提醒列表 已有计划",
        # 外部上下文受限回合也可查看计划（#489），增删计划不行。
        external_allowed=True,
    )
    tools.register(
        CancelScheduleTool(service), risk="write", search_hint="删除提醒 取消任务"
    )

    rpc = ctx.require(RPC)
    api = ScheduleApi(service, roles)
    # Reading and cancelling stay available while a reload pauses admission,
    # as the core's role task methods were; the scheduler is process-wide, so
    # whichever generation answers sees the same jobs.
    rpc.register(
        "list", api.list_tasks, concurrency=Concurrency.READ_ONLY, admission_exempt=True
    )
    rpc.register("cancel", api.cancel, admission_exempt=True)
    rpc.register("create", api.create)
    rpc.register("update", api.update)

    background = ctx.require(BACKGROUND)

    def changed(role_id: str) -> None:
        # Generations overlap while one retires; only the published one tells
        # the renderer, so each change is announced once.
        if resources.active:
            _ = background.spawn(
                rpc.emit(TASKS_CHANGED_EVENT, {"role_id": role_id}),
                name="schedule.tasks.changed",
            )

    ctx.effect("schedule.changes", service.subscribe(changed))
    ctx.provide(SCHEDULER, SchedulerPort(service))
