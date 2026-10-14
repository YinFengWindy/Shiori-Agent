"""Role-scoped task operations; external agent lifecycle remains authoritative."""

import asyncio
import time
from contextvars import Context
from uuid import uuid4
from typing import TYPE_CHECKING

from .models import CodingTask
from .cli import CommandError

if TYPE_CHECKING:
    from .service import TaskService


def owned_task(service: "TaskService", task_id: str, role_id: str) -> CodingTask:
    """Do not reveal whether another role's task identifier exists."""
    task = service.tasks.get(task_id)
    if task is None or task.target.role_id != role_id:
        raise ValueError("找不到当前角色的任务")
    return task


def task_snapshot(task: CodingTask) -> dict[str, object]:
    """Bounded task read model shared by chat and later dashboard adapters."""
    return {
        "id": task.id,
        "run_id": task.run_id,
        "role_id": task.target.role_id,
        "thread_id": task.target.thread_id,
        "agent": task.agent,
        "requirement": task.requirement,
        "repository": str(task.repository),
        "worktree": str(task.worktree or ""),
        "branch": task.branch,
        "status": task.status,
        "agent_state": task.agent_state,
        "summary": task.summary,
        "validation": list(task.validation),
        "pr_url": task.pr_url,
        "error": task.error,
        "report_error": task.report_error,
        "output": task.output[-16000:],
        "created_at": task.created_at,
        "updated_at": task.updated_at,
        "revision": task.revision,
    }


async def inspect_task(
    service: "TaskService", task_id: str, role_id: str
) -> CodingTask:
    """Refresh terminal evidence without submitting work or changing delivery claims."""
    task = owned_task(service, task_id, role_id)
    if not task.pane_id or service.closed:
        return task
    cli = service.create_cli(task.config)
    try:
        agent = (await cli.call("agent", "get", task.agent_name))["agent"]
        if service.closed:
            raise RuntimeError("Herdr 插件已停止追踪")
        if agent.get("pane_id") != task.pane_id or agent.get("agent") != task.agent:
            raise ValueError("原任务 agent 已被替换")
        task.agent_state = str(agent.get("agent_status", "unknown"))
        task.output = await cli.read(
            task.agent_name,
            source=(
                "recent-unwrapped"
                if task.agent_state in {"idle", "done"}
                else "visible"
            ),
        )
    except (CommandError, ValueError) as error:
        task.output = f"当前终端状态不可读取：{error}"
    service.changed(task)
    return task


async def continue_task(
    service: "TaskService", task_id: str, requirement: str, role_id: str
) -> CodingTask:
    """Claim a new run on the existing agent only after its preceding run stopped."""
    if service.closed:
        raise RuntimeError("Herdr 插件已停止追踪")
    if not requirement.strip():
        raise ValueError("继续任务需要完整追加要求")
    task = owned_task(service, task_id, role_id)
    async with task.operation_lock:
        if task.worker is not None and not task.worker.done():
            raise ValueError("任务仍在执行或汇报，请等待当前回合结束")
        if not task.pane_id or task.worktree is None:
            raise ValueError("任务尚无可继续的 agent/worktree")
        cli = service.create_cli(task.config)
        agent = (await cli.call("agent", "get", task.agent_name))["agent"]
        if service.closed:
            raise RuntimeError("Herdr 插件已停止追踪")
        if agent.get("pane_id") != task.pane_id or agent.get("agent") != task.agent:
            raise ValueError("原 agent 已退出或被替换，不能向其他 agent 继续")
        if agent.get("agent_status") not in {"idle", "done"}:
            task.agent_state = str(agent.get("agent_status", "unknown"))
            task.output = await cli.read(task.agent_name, source="visible")
            service.changed(task)
            raise ValueError(
                "Agent 尚未准备接收新要求；请先处理 Herdr 中的登录、初始化或交互提示"
            )
        task.run_id = uuid4().hex
        task.requirement += "\n\n用户追加要求：\n" + requirement
        task.summary = task.error = task.report_error = task.pr_url = ""
        task.validation.clear()
        task.prompt_settled = task.prompt_sent = False
        task.touch("queued")
        service.launch_run(task, continuing=True)
        return task


async def cancel_task(service: "TaskService", task_id: str, role_id: str) -> CodingTask:
    """Return cancellation admission promptly; only confirmation marks cancelled."""
    if service.closed:
        raise RuntimeError("Herdr 插件已停止追踪")
    task = owned_task(service, task_id, role_id)
    async with task.operation_lock:
        if service.closed:
            raise RuntimeError("Herdr 插件已停止追踪")
        if task.status in {"completed", "cancelled", "cancelling"}:
            return task
        task.touch("cancelling")
        previous = task.worker
        if previous is not None and not previous.done():
            previous.cancel()
        task.worker = asyncio.create_task(
            _confirm_cancel(service, task, previous),
            name=f"herdr-cancel:{task.id}",
            context=Context(),
        )
        service.changed(task)
        return task


async def _confirm_cancel(
    service: "TaskService", task: CodingTask, previous: asyncio.Task[None] | None
) -> None:
    try:
        if previous is not None:
            await asyncio.gather(previous, return_exceptions=True)
        if not task.pane_id:
            # An interrupted creation request can have succeeded remotely. There
            # is no proven target to stop, so never claim it was cancelled.
            raise ValueError("未确认 Herdr agent 身份，无法确认停止；任务可能仍在启动")
        cli = service.create_cli(task.config)
        agent = (await cli.call("agent", "get", task.agent_name))["agent"]
        if agent.get("pane_id") != task.pane_id or agent.get("agent") != task.agent:
            raise ValueError("原 agent 已被替换，未向新进程发送取消")
        if task.prompt_sent or agent.get("agent_status") not in {"idle", "done"}:
            _ = await cli.call("agent", "send-keys", task.agent_name, "ctrl+c")
            # Input is queued asynchronously; do not accept the pre-interrupt
            # idle snapshot as proof that a submitted prompt was stopped.
            await asyncio.sleep(0.5)
            deadline = time.monotonic() + task.config.cli_timeout_seconds
            while time.monotonic() < deadline:
                agent = (await cli.call("agent", "get", task.agent_name))["agent"]
                if (
                    agent.get("pane_id") != task.pane_id
                    or agent.get("agent") != task.agent
                ):
                    raise ValueError("取消后 agent 身份改变，无法确认原回合停止")
                if agent.get("agent_status") in {"idle", "done"}:
                    break
                await asyncio.sleep(0.5)
            else:
                raise TimeoutError("取消等待超时，尚未确认停止；Herdr 任务可能仍在运行")
        task.error = ""
        task.touch("cancelled")
    except asyncio.CancelledError:
        task.error = "Shiori 已停止取消确认；Herdr 任务状态未确认"
        task.touch("monitoring_stopped")
        service.changed(task)
        raise
    except Exception as error:
        task.error = str(error)
        task.touch("unknown")
    service.changed(task)
    try:
        _ = await task.target.report(
            f"{task.id}:{task.run_id}:cancel", service.report_text(task)
        )
    except Exception as error:
        task.report_error = str(error)
        service.changed(task)
