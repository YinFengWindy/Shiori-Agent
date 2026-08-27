"""Shell 后台任务注册、输出轮询与停止控制。"""

from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from agent.tools.base import Tool

from .constants import (
    _BG_EVICT_DELAY_S,
    _BG_TTL_S,
    _BLOCK_DEFAULT_MS,
    _BLOCK_MAX_MS,
    _STREAM_CHUNK_SIZE,
    _STREAM_DRAIN_GRACE_S,
)
from .output import _err, _truncate
from .runner import _invoke_kill_process_tree


@dataclass
class _BackgroundTask:
    proc: Any  # asyncio.subprocess.Process
    log_path: str
    pump_task: asyncio.Task | None   # None 仅在创建瞬间，pump 注册后立即填入
    started_at: float                # monotonic，用于 TTL 检查
    wall_started_at_ms: int          # epoch ms，返回给 LLM
    command: str = ""
    description: str = ""
    last_output_at_ms: int | None = None  # epoch ms，每次写文件时更新
    timeout_s: int | None = None
    timeout_handle: asyncio.TimerHandle | None = None
    finish_reason: str = "natural"

# 模块级单例：跨 ShellTool 实例共享
_BG_REGISTRY: dict[str, _BackgroundTask] = {}

async def _bg_pump(
    proc: Any,
    log_path: str,
    bg_task: _BackgroundTask,
    on_data: Callable[[str], None] | None = None,
) -> None:
    """持续从 stdout/stderr 读取并写入日志文件，直到进程退出（+ 短暂排水）。

    顺序：先等主进程退出，再尝试排水 grace 秒；超时则强制取消 drain task。
    这样即使子孙进程继承了 pipe fd，pump_task 也不会永久阻塞。
    每次写入时更新 bg_task.last_output_at_ms，供 LLM 判断是否卡死。
    on_data 用于前台阶段的实时流式回调（转后台后不再触发）。
    """
    with open(log_path, "wb") as f:
        async def _drain_stream(stream) -> None:
            if stream is None:
                return
            while True:
                chunk = await stream.read(_STREAM_CHUNK_SIZE)
                if not chunk:
                    break
                f.write(chunk)
                f.flush()
                bg_task.last_output_at_ms = int(time.time() * 1000)
                if on_data is not None:
                    on_data(chunk.decode(errors="replace"))

        stdout_task = asyncio.create_task(_drain_stream(proc.stdout))
        stderr_task = asyncio.create_task(_drain_stream(proc.stderr))

        # 等主进程本体退出（不等子孙进程关 fd）
        await proc.wait()

        # 短暂排水：捕获最后几帧输出；超时后强制取消
        try:
            await asyncio.wait_for(
                asyncio.gather(stdout_task, stderr_task),
                timeout=_STREAM_DRAIN_GRACE_S,
            )
        except asyncio.TimeoutError:
            stdout_task.cancel()
            stderr_task.cancel()
            await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)


def _schedule_eviction(task_id: str, log_path: str) -> None:
    """在当前事件循环上注册延迟清理（由 pump_task done callback 调用）。"""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return

    def _evict() -> None:
        task = _BG_REGISTRY.pop(task_id, None)
        if task is not None and task.timeout_handle is not None:
            task.timeout_handle.cancel()
        try:
            os.unlink(log_path)
        except OSError:
            pass

    loop.call_later(_BG_EVICT_DELAY_S, _evict)


def _on_background_task_done(task_id: str, task: _BackgroundTask) -> None:
    _schedule_eviction(task_id, task.log_path)

def _bg_kill(task_id: str, *, finish_reason: str = "stopped") -> None:
    """杀掉后台任务、从注册表移除并立即删除日志文件。"""
    task = _BG_REGISTRY.pop(task_id, None)
    if task is None:
        return
    task.finish_reason = finish_reason
    if task.timeout_handle is not None:
        task.timeout_handle.cancel()
    try:
        _invoke_kill_process_tree(task.proc)
    except (ProcessLookupError, PermissionError):
        pass
    if task.pump_task is not None:
        task.pump_task.cancel()
    try:
        os.unlink(task.log_path)
    except OSError:
        pass


def _bg_timeout(task_id: str) -> None:
    task = _BG_REGISTRY.get(task_id)
    if task is None:
        return
    _bg_kill(task_id, finish_reason="timeout")


class ShellTaskOutputTool(Tool):
    """读取后台 shell 任务的当前输出，可选择阻塞等待完成。"""

    name = "task_output"

    @property
    def description(self) -> str:
        return (
            "读取后台 shell 任务的当前输出和状态。\n"
            "返回字段：\n"
            "- status: 'running' | 'done'\n"
            "- exit_code: 进程退出码（运行中为 null）\n"
            "- elapsed_ms: 任务已运行毫秒数\n"
            "- since_last_output_ms: 距上次有输出经过的毫秒数（null 表示从未有过输出）\n"
            "- output: 最近输出内容（尾部截断到 30000 字符）\n"
            "收到 task_output 结果后，结合你对命令的了解，判断这个任务是否应该继续运行：\n"
            "需要 task_stop 终止的情况（有输出不代表不该 stop）：\n"
            "  - 任务是死循环或明确没有退出条件（无论是否产生输出）\n"
            "  - 任务挂起：有过输出但 since_last_output_ms 异常大，不符合该命令的预期节奏\n"
            "  - 任务卡死：从未有过输出（since_last_output_ms=null）且 elapsed_ms 超过合理预期\n"
            "不需要 stop 的情况：编译、下载、训练等明确会结束的长时间任务，或用户主动要求的服务进程。\n"
            "- 这是轮询接口：block=true 最多等待 timeout_ms（上限 30s）就返回一次快照，不会一直阻塞到任务结束。\n"
            "- 长任务用轮询循环：每次 block 一段→返回后判断 done/继续轮询/task_stop，不要期望一次调用就等到结束（传超大 timeout_ms 也会被钳到 30s）。\n"
            "- 分次轮询才能在等待期间响应用户新消息或 /stop；一次死等会让你长时间无响应。\n"
            "- 如果你决定放弃某个后台任务、准备输出最终回复，必须先调用 task_stop 将其终止，再生成回复。不要让后台任务在你回复后继续孤立运行。\n"
            "- 如果返回 status=done，本轮必须负责处理结果，不会有任何系统自动回传。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "shell 工具返回的 background_task_id",
                },
                "block": {
                    "type": "boolean",
                    "description": "是否等待任务完成后再返回，默认 false",
                },
                "timeout_ms": {
                    "type": "integer",
                    "description": "block=true 时本次最多等待毫秒数，默认 30000，上限 30000（超过按上限处理，单次轮询不会等到任务结束）",
                    "minimum": 0,
                    "maximum": _BLOCK_MAX_MS,
                },
            },
            "required": ["task_id"],
        }

    async def execute(self, **kwargs: Any) -> str:
        task_id: str = kwargs.get("task_id", "")
        block: bool = bool(kwargs.get("block", False))
        # 钳到硬上限：block 本质是轮询一次，单次最多等 _BLOCK_MAX_MS，避免一次调用长时间静默
        timeout_ms: int = min(max(int(kwargs.get("timeout_ms", _BLOCK_DEFAULT_MS)), 0), _BLOCK_MAX_MS)

        task = _BG_REGISTRY.get(task_id)
        if task is None:
            return _err(f"任务 {task_id!r} 不存在或已清理")

        pump_task = task.pump_task
        if pump_task is None:
            return _err(f"任务 {task_id!r} 状态异常：缺少输出泵")
        if _is_background_timeout(task):
            _bg_timeout(task_id)
            return _err(f"任务 {task_id!r} 已超时（{task.timeout_s}s），已自动终止")

        if block and not pump_task.done():
            if task.timeout_s is not None:
                remaining_ms = int(
                    max(task.timeout_s - (time.monotonic() - task.started_at), 0)
                    * 1000
                )
                timeout_ms = min(timeout_ms, remaining_ms)
            try:
                await asyncio.wait_for(
                    asyncio.shield(pump_task), timeout=timeout_ms / 1000
                )
            except asyncio.TimeoutError:
                pass
            except asyncio.CancelledError:
                current = asyncio.current_task()
                if current is not None and current.cancelling():
                    raise

        if task.finish_reason == "timeout" or _is_background_timeout(task):
            _bg_timeout(task_id)
            return _err(f"任务 {task_id!r} 已超时（{task.timeout_s}s），已自动终止")

        done = pump_task.done()
        if done and time.monotonic() - task.started_at > _BG_TTL_S:
            if task_id in _BG_REGISTRY:
                del _BG_REGISTRY[task_id]
            if task.timeout_handle is not None:
                task.timeout_handle.cancel()
            try:
                os.unlink(task.log_path)
            except OSError:
                pass
            return _err(f"任务 {task_id!r} 已超出 TTL（{_BG_TTL_S}s），已清理")

        exit_code = task.proc.returncode if done else None
        status = "done" if done else "running"

        now_ms = int(time.time() * 1000)
        elapsed_ms = now_ms - task.wall_started_at_ms
        since_last_output_ms = (
            now_ms - task.last_output_at_ms
            if task.last_output_at_ms is not None
            else None
        )

        try:
            content = Path(task.log_path).read_bytes().decode(errors="replace")
        except OSError:
            content = ""

        output_meta = _truncate(content)
        truncation = None
        if output_meta["truncated"]:
            truncation = {
                "strategy": output_meta["strategy"],
                "full_length": output_meta["full_length"],
                "returned_length": output_meta["returned_length"],
                "omitted_lines": output_meta["omitted_lines"],
            }

        return json.dumps(
            {
                "task_id": task_id,
                "status": status,
                "exit_code": exit_code,
                "elapsed_ms": elapsed_ms,
                "since_last_output_ms": since_last_output_ms,
                "output": output_meta["text"],
                "truncation": truncation,
                "output_path": task.log_path,
            },
            ensure_ascii=False,
        )


# ── ShellTaskStopTool ────────────────────────────────────────────────


class ShellTaskStopTool(Tool):
    """停止并清理一个后台 shell 任务。"""

    name = "task_stop"

    @property
    def description(self) -> str:
        return "停止后台 shell 任务（SIGKILL 整棵进程树）并从注册表移除。"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "要停止的后台任务 ID（background_task_id）",
                },
            },
            "required": ["task_id"],
        }

    async def execute(self, **kwargs: Any) -> str:
        task_id: str = kwargs.get("task_id", "")
        if task_id not in _BG_REGISTRY:
            return json.dumps(
                {"task_id": task_id, "status": "not_found"}, ensure_ascii=False
            )
        _bg_kill(task_id)
        return json.dumps({"task_id": task_id, "status": "stopped"}, ensure_ascii=False)


def _arm_background_timeout(task_id: str, task: _BackgroundTask) -> None:
    if task.timeout_s is None:
        return
    remain_s = task.timeout_s - (time.monotonic() - task.started_at)
    if remain_s <= 0:
        _bg_timeout(task_id)
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    task.timeout_handle = loop.call_later(remain_s, lambda: _bg_timeout(task_id))


def _is_background_timeout(task: _BackgroundTask) -> bool:
    if task.timeout_s is None:
        return False
    return time.monotonic() - task.started_at >= task.timeout_s
