"""Model-facing entrypoint; destination identity comes only from the host."""

import json
from typing import Any

from shiori_sdk.background_results import BackgroundResults
from shiori_sdk.tools import Tool

from .service import TaskService


class StartCodingTask(Tool):
    """Delegate a complete development request to a local Full Access coding agent."""

    name = "herdr_start_task"
    description = (
        "通过本机 Herdr 在独立 worktree 执行开发任务（Full Access），"
        "支持 Codex/Claude Code。传入完整需求和 Git 仓库绝对路径；"
        "立即返回任务编号，完成实际验证并创建 Draft PR 后回报原聊天。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "repository": {
                "type": "string",
                "description": "本机 Git 仓库根目录绝对路径",
            },
            "requirement": {
                "type": "string",
                "description": "完整需求、约束及验收条件",
            },
            "agent": {"type": "string", "enum": ["codex", "claude"]},
        },
        "required": ["repository", "requirement"],
    }

    def __init__(self, service: TaskService, results: BackgroundResults) -> None:
        self.service = service
        self.results = results

    async def execute(self, **kwargs: Any) -> str:
        """Model arguments cannot choose a role, thread, or outbound destination."""
        agent = kwargs.get("agent", self.service.cli.config.default_agent)
        if agent not in {"codex", "claude"}:
            raise ValueError("agent 只支持 codex 或 claude")
        task = self.service.start(
            kwargs["repository"], kwargs["requirement"], agent, self.results.capture()
        )
        return json.dumps(
            {"task_id": task.id, "status": task.status, "agent": task.agent},
            ensure_ascii=False,
        )
