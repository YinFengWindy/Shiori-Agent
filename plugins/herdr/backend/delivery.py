"""Task instructions and verification of the coding agent's delivery artifacts."""

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from .cli import CommandError, HerdrCli
from .models import CodingTask


class ValidationCommand(BaseModel):
    """An argv command to reproduce one actual validation in the task checkout."""

    model_config = ConfigDict(extra="forbid")
    argv: list[str] = Field(min_length=1)
    cwd: str = "."


class DeliveryResult(BaseModel):
    """A result is a claim until the plugin verifies commit, tests and Draft PR."""

    model_config = ConfigDict(extra="forbid")
    task_id: str
    run_id: str
    status: str
    summary: str = Field(min_length=1)
    validation: list[ValidationCommand] = Field(default_factory=list)
    pr_url: str = ""
    blockers: list[str] = Field(default_factory=list)


def write_instructions(task: CodingTask) -> Path:
    """Keep complete Unicode requirements in a file outside the Git checkout."""
    path = task.directory / f"{task.run_id}.md"
    schema = {
        "task_id": task.id,
        "run_id": task.run_id,
        "status": "completed 或 blocked",
        "summary": "实际修改摘要",
        "validation": [{"argv": ["实际测试程序", "参数"], "cwd": "."}],
        "pr_url": "真实 Draft PR URL",
        "blockers": [],
    }
    _ = path.write_text(
        f"你在 Shiori 的独立 Coding Agent 任务中工作。task={task.id} run={task.run_id}\n"
        f"仓库：{task.repository}\n工作目录：{task.worktree}\n分支：{task.branch}\n"
        "权限为 Full Access。遵守仓库 AGENTS 和用户完整需求，在当前独立 worktree 修改。"
        "完成与范围匹配的实际验证，提交并推送当前分支、创建 Draft PR；禁止合并 PR。"
        "不要删除 worktree 或切换分支。缺少登录/工具/配置或验证失败时明确报告阻塞。\n"
        "验证命令使用 argv 数组，不使用 shell 拼接；cwd 必须位于当前 worktree，"
        "插件会重跑这些命令核验结果。不能使用仅打印成功的命令冒充测试。\n"
        "最终把如下结构的 JSON 写入指定结果路径（UTF-8，建议先写临时文件后原子替换）。"
        "只在完成所有操作后写入，不得复制旧任务结果。\n"
        f"结果路径：{task.result_path}\n"
        f"{json.dumps(schema, ensure_ascii=False, indent=2)}\n\n"
        "以下是用户完整需求，保持原意执行：\n\n" + task.requirement,
        encoding="utf-8",
    )
    return path


async def verify_delivery(task: CodingTask, cli: HerdrCli) -> None:
    """Check this attempt's result against local Git and authoritative GitHub data."""
    if task.worktree is None:
        raise ValueError("任务缺少独立 worktree")
    if task.result_path.stat().st_size > 262144:
        raise ValueError("任务结果文件过大")
    result = DeliveryResult.model_validate_json(
        task.result_path.read_text(encoding="utf-8")
    )
    if result.task_id != task.id or result.run_id != task.run_id:
        raise ValueError("结果不属于当前任务回合")
    task.summary = result.summary
    if result.status != "completed" or result.blockers:
        raise ValueError(
            "任务未交付：" + "；".join(result.blockers or [result.summary])
        )
    if not result.validation or not result.pr_url.startswith("https://"):
        raise ValueError("交付缺少实际验证命令或 Draft PR")

    async def git(*args: str) -> str:
        return (await cli.command(["git", *args], cwd=task.worktree)).strip()

    if await git("branch", "--show-current") != task.branch:
        raise ValueError("任务分支已改变")
    if await git("status", "--porcelain"):
        raise ValueError("worktree 仍有未提交修改")
    head = await git("rev-parse", "HEAD")
    if head == task.base_commit or not await git(
        "diff", "--name-only", task.base_commit, "HEAD"
    ):
        raise ValueError("任务没有可验证的代码修改")
    task.validation.clear()
    for check in result.validation:
        cwd = (task.worktree / check.cwd).resolve()
        if not cwd.is_relative_to(task.worktree.resolve()):
            raise ValueError("验证工作目录超出任务 worktree")
        try:
            output = await cli.command(check.argv, cwd=cwd)
        except CommandError as error:
            task.validation.append(
                {
                    "argv": check.argv,
                    "cwd": check.cwd,
                    "exit_code": error.exit_code,
                    "output": str(error),
                }
            )
            raise
        task.validation.append(
            {
                "argv": check.argv,
                "cwd": check.cwd,
                "exit_code": 0,
                "output": output[-8000:],
            }
        )
    # Verification may generate tracked files; the PR must refer to the checked head.
    if await git("status", "--porcelain") or await git("rev-parse", "HEAD") != head:
        raise ValueError("验证改变了交付工作树或提交")
    raw = await cli.command(
        [
            "gh",
            "pr",
            "view",
            task.branch,
            "--json",
            "url,isDraft,state,headRefName,headRefOid,baseRefName",
        ],
        cwd=task.worktree,
    )
    pr = json.loads(raw)
    if (
        pr.get("url") != result.pr_url
        or pr.get("isDraft") is not True
        or pr.get("state") != "OPEN"
        or pr.get("headRefName") != task.branch
        or pr.get("headRefOid") != head
        or pr.get("baseRefName") == task.branch
    ):
        raise ValueError("PR 不是当前已验证提交的开放 Draft PR")
    task.pr_url = result.pr_url
