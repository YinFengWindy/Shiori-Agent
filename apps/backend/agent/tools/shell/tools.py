"""ShellTool 的前台、后台与自动提升编排。"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, cast
from uuid import uuid4

from agent.tools.base import Tool

from .background import (
    _BG_REGISTRY,
    _BackgroundTask,
    _arm_background_timeout,
    _bg_pump,
    _on_background_task_done,
)
from .constants import (
    _BANNED,
    _BLOCKING_TIMEOUT,
    _DEFAULT_TIMEOUT,
    _FG_THRESHOLD,
    _MAX_TIMEOUT,
    _STREAM_DRAIN_GRACE_S,
)
from .environment import _shell_env
from .output import _err, _truncate, _write_full_output
from .runner import _invoke_kill_process_tree, _subprocess_options
from .validation import _validate_command

logger = logging.getLogger("agent.tools.shell")


class ShellTool(Tool):
    """在 bash 中执行命令，返回结构化结果"""

    name = "shell"

    def __init__(
        self,
        *,
        allow_network: bool = True,
        working_dir: Path | None = None,
        restricted_dir: Path | None = None,
        spawn_hook: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ) -> None:
        self._allow_network = allow_network
        self._working_dir = working_dir
        self._restricted_dir = restricted_dir.resolve() if restricted_dir else None
        self._spawn_hook = spawn_hook

    @property
    def description(self) -> str:
        return (
            "在 bash 中执行命令并返回输出。\n"
            "注意：\n"
            "- 使用绝对路径，避免依赖 cd 切换目录\n"
            "- 多条命令用 ; 或 && 连接，不要用换行分隔\n"
            "- 网络命令（curl/wget/httpie/xh）仅允许访问公网 HTTP(S)，且禁止上传/写文件\n"
            "- 以下命令被禁止：nc、telnet、浏览器等高风险工具\n"
            "- 输出超过 30000 字符时自动截断\n"
            "- 前台阻塞总超时默认 60 秒，普通命令最大 600 秒\n"
            "- 命令超过 15 秒未完成时默认自动转为后台任务，返回 background_task_id；后台会沿用当前 timeout 作为硬截止时间\n"
            "- 只有用户明确说“阻塞”时，才设置 auto_promote=false；未显式传 timeout 时会默认阻塞 21600 秒\n"
            "- 服务进程或已知长时间运行的命令，直接用 run_in_background=true 后台启动，跳过 15 秒等待；后台模式只有显式传 timeout 时才会按 timeout 自动终止\n"
            "- 收到 background_task_id 后，由你负责用 task_output 主动查看进展和结果；不会有系统自动回传\n"
            "- task_output 是轮询接口：block=true 单次最多等 30s 就返回快照（不会等到任务结束），长任务靠多次轮询推进\n"
            "- 如果决定放弃后台任务并准备最终回复，必须先调用 task_stop 终止它\n"
            "禁止用途：不得用 shell 替代专用工具（read_file 读文件、web_fetch 抓网页、list_dir 列目录）。"
        )
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "要执行的 bash 命令",
                },
                "description": {
                    "type": "string",
                    "description": (
                        "用 5-10 字描述这条命令的作用，便于用户审查和日志追踪。"
                        "示例：'列出当前目录文件' / '安装 Python 依赖' / '查看进程状态'"
                    ),
                },
                "timeout": {
                    "type": "integer",
                    "description": (
                        f"前台阻塞或显式硬超时秒数，默认 {_DEFAULT_TIMEOUT}。"
                        f"普通命令最大 {_MAX_TIMEOUT}；auto_promote=false 时最大 {_BLOCKING_TIMEOUT}。"
                        "自动转后台后只有显式传入才生效。"
                    ),
                    "minimum": 1,
                    "maximum": _BLOCKING_TIMEOUT,
                },
                "run_in_background": {
                    "type": "boolean",
                    "description": (
                        "是否后台运行。设为 true 时立即返回 background_task_id，"
                        "输出写入日志文件，通过 task_output 获取、task_stop 停止。"
                        "适用于服务进程、长时间编译等不需要等待结果的场景。"
                    ),
                },
                "auto_promote": {
                    "type": "boolean",
                    "description": (
                        "前台命令超过 15 秒未完成时是否自动转后台，默认 true。"
                        "只有用户明确说“阻塞”时才设为 false；不传 timeout 时默认等待 21600 秒。"
                    ),
                },
            },
            "required": ["command", "description"],
        }

    async def execute(self, **kwargs: Any) -> str:
        command: str = kwargs.get("command", "").strip()
        description: str = kwargs.get("description", "")
        timeout_specified = "timeout" in kwargs and kwargs.get("timeout") is not None
        run_in_background: bool = bool(kwargs.get("run_in_background", False))
        auto_promote: bool = bool(kwargs.get("auto_promote", True))
        max_timeout = (
            _BLOCKING_TIMEOUT
            if not run_in_background and not auto_promote
            else _MAX_TIMEOUT
        )
        default_timeout = (
            _BLOCKING_TIMEOUT
            if not run_in_background and not auto_promote and not timeout_specified
            else _DEFAULT_TIMEOUT
        )
        timeout: int = min(int(kwargs.get("timeout", default_timeout)), max_timeout)
        on_data = kwargs.get("_on_data")

        if not command:
            return _err("命令不能为空")

        cwd = self._working_dir
        env = _shell_env()
        if self._spawn_hook is not None:
            hooked = self._spawn_hook(
                {
                    "command": command,
                    "cwd": str(cwd) if cwd is not None else None,
                    "env": env,
                }
            )
            command = str(hooked.get("command", command)).strip()
            cwd_val = hooked.get("cwd")
            cwd = None if cwd_val in (None, "") else Path(str(cwd_val))
            env_val = hooked.get("env")
            if isinstance(env_val, dict):
                env = {str(k): str(v) for k, v in env_val.items()}

        if self._restricted_dir is not None and cwd is None:
            cwd = self._restricted_dir

        logger.info("shell [%s]: %s", description, command[:120])

        base_cmd = command.split()[0].lower()
        if base_cmd in _BANNED:
            return _err(f"命令 '{base_cmd}' 不被允许（安全限制）")
        cmd_err = _validate_command(
            command,
            allow_network=self._allow_network,
            restricted_dir=self._restricted_dir,
            cwd=cwd,
        )
        if cmd_err:
            return _err(cmd_err)

        if run_in_background:
            bg_timeout = timeout if timeout_specified else None
            return await self._execute_background(
                command, description, cwd, env, bg_timeout
            )

        # ── 前台路径（默认 15s 未完成自动转后台）──────────────────────
        data_callback = (
            cast(Callable[[str], None], on_data) if callable(on_data) else None
        )
        return await self._execute_with_auto_promote(
            command,
            description,
            cwd,
            env,
            timeout,
            timeout_specified,
            data_callback,
            auto_promote,
        )

    async def _execute_background(
        self,
        command: str,
        description: str,
        cwd: Path | None,
        env: dict[str, str],
        timeout_s: int | None,
    ) -> str:
        task_id = f"shell_{uuid4().hex[:12]}"
        log_fd, log_path = tempfile.mkstemp(
            prefix=f"akashic-bg-{task_id}-", suffix=".log"
        )
        os.close(log_fd)

        wall_start_ms = int(time.time() * 1000)
        proc = await asyncio.create_subprocess_shell(
            command,
            **_subprocess_options(cwd, env),
        )
        # 先建 bg_task 对象，pump 需要引用它来更新 last_output_at_ms
        bg = _BackgroundTask(
            proc=proc,
            log_path=log_path,
            pump_task=None,
            started_at=time.monotonic(),
            wall_started_at_ms=wall_start_ms,
            command=command,
            description=description,
            timeout_s=timeout_s,
        )
        pump = asyncio.create_task(_bg_pump(proc, log_path, bg))
        pump.add_done_callback(lambda _: _on_background_task_done(task_id, bg))
        bg.pump_task = pump
        _BG_REGISTRY[task_id] = bg
        _arm_background_timeout(task_id, bg)
        logger.info("shell bg started [%s] pid=%s log=%s", task_id, proc.pid, log_path)

        return json.dumps(
            {
                "command": command,
                "background_task_id": task_id,
                "status": "running",
                "output_path": log_path,
                "started_at_ms": wall_start_ms,
                "timeout_s": timeout_s,
                "exit_code": None,
                "interrupted": False,
            },
            ensure_ascii=False,
        )

    async def _execute_with_auto_promote(
        self,
        command: str,
        description: str,
        cwd: Path | None,
        env: dict[str, str],
        timeout: int,
        timeout_specified: bool,
        on_data: Callable[[str], None] | None,
        auto_promote: bool,
    ) -> str:
        """前台执行；允许按需关闭自动转后台，直接等待完整结果。"""
        task_id = f"shell_{uuid4().hex[:12]}"
        log_fd, log_path = tempfile.mkstemp(
            prefix=f"akashic-fg-{task_id}-", suffix=".log"
        )
        os.close(log_fd)

        wall_start_ms = int(time.time() * 1000)
        start_mono = time.monotonic()
        hard_timeout_s = timeout

        proc = await asyncio.create_subprocess_shell(
            command,
            **_subprocess_options(cwd, env),
        )
        bg = _BackgroundTask(
            proc=proc,
            log_path=log_path,
            pump_task=None,
            started_at=start_mono,
            wall_started_at_ms=wall_start_ms,
            command=command,
            description=description,
            timeout_s=hard_timeout_s,
        )
        pump = asyncio.create_task(_bg_pump(proc, log_path, bg, on_data))
        bg.pump_task = pump

        fg_wait_timeout = min(timeout, _FG_THRESHOLD) if auto_promote else timeout
        try:
            await asyncio.wait_for(asyncio.shield(pump), timeout=fg_wait_timeout)
        except asyncio.TimeoutError:
            elapsed_s = time.monotonic() - start_mono
            if not auto_promote or (timeout_specified and elapsed_s >= timeout):
                return await self._finalize_timed_out_process(
                    command, proc, pump, log_path, start_mono
                )
            # ── 自动转后台 ──────────────────────────────────────────────
            pump.add_done_callback(lambda _: _on_background_task_done(task_id, bg))
            _BG_REGISTRY[task_id] = bg
            _arm_background_timeout(task_id, bg)
            logger.info(
                "shell auto-promoted [%s] pid=%s log=%s", task_id, proc.pid, log_path
            )
            return json.dumps(
                {
                    "command": command,
                    "background_task_id": task_id,
                    "status": "running",
                    "output_path": log_path,
                    "started_at_ms": wall_start_ms,
                    "timeout_s": hard_timeout_s,
                    "exit_code": None,
                    "interrupted": False,
                    "auto_promoted": True,
                },
                ensure_ascii=False,
            )
        except asyncio.CancelledError:
            # 外层被取消 → 杀掉进程并清理
            try:
                _invoke_kill_process_tree(proc)
            except (ProcessLookupError, PermissionError):
                pass
            pump.cancel()
            try:
                os.unlink(log_path)
            except OSError:
                pass
            raise

        # ── 前台正常完成 ────────────────────────────────────────────────
        duration_ms = int((time.monotonic() - start_mono) * 1000)
        exit_code = proc.returncode or 0

        try:
            content = Path(log_path).read_bytes().decode(errors="replace")
        except OSError:
            content = ""
        finally:
            try:
                os.unlink(log_path)
            except OSError:
                pass

        if not content:
            content = "（无输出）"
        elif exit_code != 0:
            content = content + f"\nExit code {exit_code}"

        output_meta = _truncate(content)
        full_output_path = _write_full_output(content) if output_meta["truncated"] else None
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
                "command": command,
                "exit_code": exit_code,
                "interrupted": False,
                "duration_ms": duration_ms,
                "output": output_meta["text"],
                "truncation": truncation,
                "full_output_path": full_output_path,
            },
            ensure_ascii=False,
        )

    async def _finalize_timed_out_process(
        self,
        command: str,
        proc: Any,
        pump: asyncio.Task,
        log_path: str,
        start_mono: float,
    ) -> str:
        try:
            _invoke_kill_process_tree(proc)
        except (ProcessLookupError, PermissionError):
            pass

        try:
            await asyncio.wait_for(asyncio.shield(pump), timeout=_STREAM_DRAIN_GRACE_S)
        except asyncio.TimeoutError:
            pump.cancel()
            await asyncio.gather(pump, return_exceptions=True)

        duration_ms = int((time.monotonic() - start_mono) * 1000)
        try:
            content = Path(log_path).read_bytes().decode(errors="replace")
        except OSError:
            content = ""
        finally:
            try:
                os.unlink(log_path)
            except OSError:
                pass

        if not content:
            content = "（无输出）"
        content = content + "\nCommand timed out"
        output_meta = _truncate(content)
        full_output_path = _write_full_output(content) if output_meta["truncated"] else None
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
                "command": command,
                "exit_code": -1,
                "interrupted": True,
                "duration_ms": duration_ms,
                "output": output_meta["text"],
                "truncation": truncation,
                "full_output_path": full_output_path,
            },
            ensure_ascii=False,
        )
