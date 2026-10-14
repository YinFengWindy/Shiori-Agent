"""Shared in-process task service for chat tools and the subsequent dashboard."""

import asyncio
import json
import time
from pathlib import Path
from uuid import uuid4

from shiori_sdk.background_results import BackgroundResultTarget
from shiori_sdk.processes import Processes
from contextvars import Context
from collections.abc import Callable

from .cli import CommandError, HerdrCli
from .config import AgentKind, HerdrConfig
from .delivery import verify_delivery, write_instructions
from .models import CodingTask
from .task_management import cancel_task, continue_task, inspect_task


class TaskService:
    """Own task records and observers; Herdr owns the coding agent processes."""

    def __init__(self, directory: Path, processes: Processes) -> None:
        self.directory = directory
        self.processes = processes
        self.tasks: dict[str, CodingTask] = {}
        self.closed = False
        self._listeners: set[Callable[[CodingTask], None]] = set()

    def create_cli(self, config: HerdrConfig) -> HerdrCli:
        """Build a stateless adapter using the task's immutable session configuration."""
        return HerdrCli(config, self.processes, self.directory)

    # Keep operations bound to this owner's import generation. New tool/RPC
    # facades must not mix their CommandError class with the retained CLI's.
    async def inspect_task(self, task_id: str, role_id: str) -> CodingTask:
        """Refresh this role's task using the retained owner's CLI boundary."""
        return await inspect_task(self, task_id, role_id)

    async def continue_task(
        self, task_id: str, requirement: str, role_id: str
    ) -> CodingTask:
        """Accept another run on this role's existing agent and worktree."""
        return await continue_task(self, task_id, requirement, role_id)

    async def cancel_task(self, task_id: str, role_id: str) -> CodingTask:
        """Accept cancellation and track confirmation in the retained owner."""
        return await cancel_task(self, task_id, role_id)

    def subscribe(self, listener: Callable[[CodingTask], None]) -> Callable[[], None]:
        """Observe in-process snapshots; registration belongs to the calling view."""
        self._listeners.add(listener)
        return lambda: self._listeners.discard(listener)

    def changed(self, task: CodingTask) -> None:
        """Publish a new revision after task mutations."""
        task.touch()
        for listener in tuple(self._listeners):
            listener(task)

    async def close(self) -> None:
        """Stop monitors without killing the shared Herdr server or deleting work."""
        self.closed = True
        workers = [
            task.worker
            for task in self.tasks.values()
            if task.worker and not task.worker.done()
        ]
        for worker in workers:
            worker.cancel()
        outcomes = await asyncio.gather(*workers, return_exceptions=True)
        for task in self.tasks.values():
            if task.status in {"queued", "preparing", "running", "cancelling"}:
                task.error = "Shiori 已停止追踪；Herdr 中的任务可能仍在运行。"
                task.touch("monitoring_stopped")
                self.changed(task)
        self._listeners.clear()
        errors = [error for error in outcomes if isinstance(error, Exception)]
        if errors:
            raise ExceptionGroup("Herdr 任务监控清理失败", errors)

    def start(
        self,
        repository: str,
        requirement: str,
        agent: AgentKind,
        target: BackgroundResultTarget,
        config: HerdrConfig,
    ) -> CodingTask:
        """Return an identifier immediately; every external operation is background work."""
        if self.closed:
            raise RuntimeError("Herdr 插件已停止追踪")
        if agent not in {"codex", "claude"}:
            raise ValueError("agent 只支持 codex 或 claude")
        repo = Path(repository).expanduser()
        if not repo.is_absolute() or not repo.is_dir():
            raise ValueError("repository 必须是本机 Git 仓库的绝对目录")
        if not requirement.strip():
            raise ValueError("任务需求不能为空")
        task_id = uuid4().hex
        task = CodingTask(
            id=task_id,
            config=config.model_copy(deep=True),
            requirement=requirement,
            repository=repo.resolve(),
            agent=agent,
            target=target,
            directory=self.directory / "tasks" / task_id,
            branch=f"codex/herdr-{task_id[:12]}",
            run_id=uuid4().hex,
            agent_name=f"shiori-{task_id[:20]}",
        )
        task.directory.mkdir(parents=True)
        self.tasks[task_id] = task
        self.launch_run(task)
        return task

    def launch_run(self, task: CodingTask, *, continuing: bool = False) -> None:
        """Own a detached monitor without inheriting a retired runtime's context."""
        task.worker = asyncio.create_task(
            self._execute(task, continuing=continuing),
            name=f"herdr:{task.id}",
            context=Context(),
        )
        self.changed(task)

    async def _execute(self, task: CodingTask, *, continuing: bool = False) -> None:
        try:
            if continuing:
                await self._submit(task)
            else:
                await self._prepare(task)
            await self._observe(task)
        except asyncio.CancelledError:
            if task.status == "cancelling":
                raise
            task.error = "Shiori 已停止追踪；Herdr 中的任务可能仍在运行。"
            task.touch("monitoring_stopped")
            self.changed(task)
            raise
        except Exception as error:
            # This is the task boundary: persist actionable failure, never silently
            # retry an uncertain start or prompt, and keep the user's checkout.
            task.error = str(error)
            uncertain = isinstance(error, CommandError) and error.code in {
                "timeout",
                "agent_prompt_stalled",
                "invalid_response",
            }
            task.touch("unknown" if uncertain else "blocked")
        self.changed(task)
        try:
            _ = await task.target.report(
                f"{task.id}:{task.run_id}", self.report_text(task)
            )
        except Exception as error:
            task.report_error = str(error)
            self.changed(task)

    async def _prepare(self, task: CodingTask) -> None:
        cli = self.create_cli(task.config)
        task.touch("preparing")
        await cli.require_supported_version()
        actual = (
            await cli.command(
                ["git", "rev-parse", "--show-toplevel"], cwd=task.repository
            )
        ).strip()
        if Path(actual).resolve() != task.repository:
            raise ValueError("repository 必须指向 Git 仓库根目录")
        task.base_commit = (
            await cli.command(["git", "rev-parse", "HEAD"], cwd=task.repository)
        ).strip()
        worktree = self.directory / "worktrees" / task.id
        worktree.parent.mkdir(parents=True, exist_ok=True)
        created = await cli.call(
            "worktree",
            "create",
            "--cwd",
            str(task.repository),
            "--branch",
            task.branch,
            "--base",
            task.base_commit,
            "--path",
            str(worktree),
            "--label",
            task.agent_name,
            "--no-focus",
        )
        task.worktree = Path(created["worktree"]["path"]).resolve()
        if (
            task.worktree != worktree.resolve()
            or created["worktree"]["branch"] != task.branch
        ):
            raise ValueError("Herdr 创建的 worktree 与任务不一致")
        task.pane_id = created["root_pane"]["pane_id"]
        task.workspace_id = created["workspace"]["workspace_id"]
        try:
            _ = await cli.call(
                "agent",
                "start",
                task.agent_name,
                "--kind",
                task.agent,
                "--pane",
                task.pane_id,
                "--timeout",
                "30000",
                "--",
                *cli.config.agent_args(task.agent),
            )
        except CommandError as error:
            if error.code == "agent_not_ready":
                task.agent_state = "blocked"
                task.output = await cli.read(task.pane_id, source="visible")
                raise CommandError(
                    f"Agent 尚未就绪（可能需要更新确认、目录信任或登录）：{error}\n{task.output}",
                    code=error.code,
                ) from error
            raise
        await self._submit(task)

    async def _submit(self, task: CodingTask) -> None:
        cli = self.create_cli(task.config)
        instructions = write_instructions(task)
        task.touch("running")
        task.prompt_sent = True
        self.changed(task)
        try:
            response = await cli.call(
                "agent",
                "prompt",
                task.agent_name,
                f"Read the complete task instructions from the UTF-8 file {json.dumps(str(instructions), ensure_ascii=False)} and execute them. Write the required result artifact when finished.",
                "--wait",
                "--timeout",
                "5000",
            )
            task.prompt_settled = response["agent"]["agent_status"] in {"idle", "done"}
        except CommandError as error:
            if error.code not in {"timeout", "agent_prompt_stalled"}:
                raise
            # A timed-out request may already have been accepted. Observe this
            # same agent and task artifact; never submit the requirement again.
            task.error = str(error)

    async def _observe(self, task: CodingTask) -> None:
        cli = self.create_cli(task.config)
        deadline = time.monotonic() + cli.config.task_timeout_seconds
        observed_work = False
        while time.monotonic() < deadline:
            observed = await cli.call("agent", "get", task.agent_name)
            agent = observed["agent"]
            if agent.get("pane_id") != task.pane_id:
                raise ValueError("Herdr agent 已不属于原任务 pane")
            if agent.get("agent") != task.agent:
                raise ValueError("Herdr pane 中的 agent 已被替换")
            task.agent_state = str(agent["agent_status"])
            observed_work = observed_work or task.agent_state == "working"
            try:
                task.output = await cli.read(
                    task.agent_name,
                    source=(
                        "recent-unwrapped"
                        if task.agent_state in {"idle", "done"}
                        else "visible"
                    ),
                )
            except CommandError as error:
                # Output is diagnostic, not lifecycle authority. A state change
                # between get/read can make alternate-screen history unavailable;
                # keep observing the agent instead of abandoning accepted work.
                task.output = f"终端输出暂不可读：{error}"
            self.changed(task)
            if task.agent_state == "blocked":
                task.error = "Agent 等待登录、初始化或交互输入：\n" + task.output
                task.touch("blocked")
                return
            if task.agent_state in {"idle", "done"} and task.result_path.is_file():
                await verify_delivery(task, cli)
                task.error = ""
                task.touch("completed")
                return
            if task.agent_state in {"idle", "done"} and (
                task.prompt_settled or observed_work
            ):
                task.error = "Agent 已停止输出，但未提供本回合结果文件，交付未确认。"
                task.touch("blocked")
                return
            # idle/done with no result is not delivery. Startup animations and
            # stale lifecycle observations may precede actual task execution.
            await asyncio.sleep(2)
        task.error = "追踪超时，未确认交付；Herdr 任务可能仍在运行。未取消或重发。"
        task.touch("unknown")

    @staticmethod
    def report_text(task: CodingTask) -> str:
        """Evidence included in the original role's report, including failures."""
        return json.dumps(
            {
                "task_id": task.id,
                "status": task.status,
                "agent": task.agent,
                "agent_state": task.agent_state,
                "repository": str(task.repository),
                "worktree": str(task.worktree or ""),
                "branch": task.branch,
                "summary": task.summary,
                "validation": task.validation,
                "draft_pr": task.pr_url,
                "error": task.error,
            },
            ensure_ascii=False,
        )
