"""Task tools read role identity from the current host execution context."""

import json
from typing import Any

from shiori_sdk.process_resources import PluginProcessResources
from shiori_sdk.background_results import BackgroundResults
from shiori_sdk.tools import Tool, ToolsCapability

from .service import TaskService
from .task_management import cancel_task, continue_task, inspect_task, task_snapshot


class TaskManagementTool(Tool):
    """List, inspect, continue or cancel only the current role's coding tasks."""

    def __init__(
        self,
        service: TaskService,
        tools: ToolsCapability,
        resources: PluginProcessResources,
        action: str,
        results: BackgroundResults,
    ) -> None:
        self.service, self.tools, self.resources, self.action = (
            service,
            tools,
            resources,
            action,
        )
        self.results = results

    @property
    def name(self) -> str:
        return (
            f"herdr_{self.action}_task" if self.action != "list" else "herdr_list_tasks"
        )

    @property
    def description(self) -> str:
        return {
            "list": "列出当前角色通过 Herdr 发起的 Coding Agent 任务。",
            "get": "查看当前角色 Herdr 任务的状态、工作区、最近输出与交付结果。",
            "continue": "追加完整要求，在原 worktree 和同一 agent 开始新的任务回合；执行中不能重复提交。",
            "cancel": "请求停止当前角色的指定 Herdr 任务；只有确认 agent 已停止回合后才显示已取消，保留工作成果。",
        }[self.action]

    @property
    def parameters(self) -> dict[str, Any]:
        properties = {} if self.action == "list" else {"task_id": {"type": "string"}}
        required = [] if self.action == "list" else ["task_id"]
        if self.action == "continue":
            properties["requirement"] = {
                "type": "string",
                "description": "完整追加需求",
            }
            required.append("requirement")
        return {"type": "object", "properties": properties, "required": required}

    async def execute(self, **kwargs: Any) -> str:
        """Arguments cannot supply role authority or change the task's session."""
        if not self.resources.active:
            raise RuntimeError("插件配置已替换，请重新调用当前工具")
        role_id = self.tools.get_context().get("role_id", "")
        if not role_id:
            raise PermissionError("任务管理需要当前角色身份")
        if self.action == "list":
            return json.dumps(
                {
                    "tasks": [
                        task_snapshot(task)
                        for task in self.service.tasks.values()
                        if task.target.role_id == role_id
                    ]
                },
                ensure_ascii=False,
            )
        if self.action == "get":
            task = await inspect_task(self.service, kwargs["task_id"], role_id)
        elif self.action == "continue":
            _ = self.results.capture()
            task = await continue_task(
                self.service, kwargs["task_id"], kwargs["requirement"], role_id
            )
        else:
            _ = self.results.capture()
            task = await cancel_task(self.service, kwargs["task_id"], role_id)
        return json.dumps(task_snapshot(task), ensure_ascii=False)
