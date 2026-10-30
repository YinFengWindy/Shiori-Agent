from __future__ import annotations

from pathlib import Path

from agent.scheduler import LatencyTracker, SchedulerService
from agent.tools.registry import ToolRegistry
from agent.tools.schedule import CancelScheduleTool, ListSchedulesTool, ScheduleTool
from core.roles.store import RoleStore
from bootstrap.toolsets.protocol import (
    ToolsetDeps,
    ToolsetProvider,
    build_registration_result,
)
from shiori_sdk.core.schedule_host import ScheduleHost


class SchedulerToolsetProvider(ToolsetProvider):
    def register(self, registry: ToolRegistry, deps: ToolsetDeps):
        before = set(registry._tools.keys())
        scheduler = deps.scheduler
        if scheduler is None:
            raise RuntimeError("SchedulerToolsetProvider requires scheduler")
        registry.register(
            ScheduleTool(scheduler),
            risk="write",
            search_hint="cron timer 延时执行",
        )
        registry.register(
            ListSchedulesTool(scheduler),
            risk="read-only",
            search_hint="提醒列表 已有计划",
            # 外部上下文受限回合也可查看计划（#489），增删计划不行。
            external_allowed=True,
        )
        registry.register(
            CancelScheduleTool(scheduler),
            risk="write",
            search_hint="删除提醒 取消任务",
        )
        return build_registration_result(
            registry=registry,
            source_name="schedule",
            before=before,
            extras={"scheduler": scheduler},
        )


def build_scheduler(
    workspace: Path,
    host: ScheduleHost,
    *,
    role_store: RoleStore | None = None,
) -> SchedulerService:
    """Builds a scheduler that validates persisted owners against the role store."""
    roles = role_store if role_store is not None else RoleStore(workspace)
    return SchedulerService(
        store_path=workspace / "schedules.json",
        host=host,
        tracker=LatencyTracker(),
        role_exists=lambda role_id: roles.get_role(role_id) is not None,
    )
