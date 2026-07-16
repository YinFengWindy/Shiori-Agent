"""Coding CLI 适配器的公共契约与不可变运行快照。"""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator, Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from coding_agents.models import PermissionLevel

from .process import ManagedProcess, ProcessRunner


class AdapterError(RuntimeError):
    """携带稳定错误码的适配器边界异常。"""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        exit_code: int | None = None,
        stderr: str = "",
    ) -> None:
        super().__init__(message)
        self.code = code
        self.exit_code = exit_code
        self.stderr = stderr


def validate_session_id(session_id: str, provider: str) -> str:
    """Reject option-like or ambiguous provider session identifiers."""

    normalized = session_id.strip()
    if normalized != session_id or re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._:-]{0,255}",
        normalized,
    ) is None:
        raise AdapterError(
            "session_unrecoverable",
            f"{provider} session ID 格式无效",
        )
    return normalized


@dataclass(frozen=True)
class ProbeResult:
    """CLI 可用性与能力探测结果。"""

    available: bool
    version: str | None = None
    sandbox_available: bool = False
    error: str | None = None
    error_code: str | None = None


@dataclass(frozen=True)
class TaskRunSpec:
    """启动 Coding CLI 所需的结构化 Run 快照。"""

    run_id: str
    task: str
    worktree: Path
    model: str
    effort: str
    permission_level: PermissionLevel | str
    timeout_seconds: float
    environment: Mapping[str, str] = field(default_factory=dict)
    sandbox_profile: str | None = None
    max_budget_usd: float | None = None
    output_file: Path | None = None


@dataclass(frozen=True)
class ResumeSpec:
    """使用明确 Provider session 恢复一次运行。"""

    run: TaskRunSpec
    session_id: str


@dataclass(frozen=True)
class PreparedRun:
    """已验证且可直接交给进程层的启动参数。"""

    spec: TaskRunSpec
    command: tuple[str, ...]
    cwd: Path
    stdin: bytes
    environment: Mapping[str, str]
    output_file: Path | None = None
    expected_session_id: str | None = None


@dataclass(frozen=True)
class AdapterEvent:
    """Provider 原始事件转换后的统一事件。"""

    event_type: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    raw: Mapping[str, Any] | None = None


@dataclass
class RunHandle:
    """进程运行句柄及流式消费过程中收集的状态。"""

    prepared: PreparedRun
    process: ManagedProcess
    session_id: str | None = None
    stderr: str = ""
    exit_code: int | None = None
    timed_out: bool = False
    cancelled: bool = False
    error_code: str | None = None
    error_message: str | None = None
    events: list[AdapterEvent] = field(default_factory=list)


@dataclass(frozen=True)
class AdapterResult:
    """Run 结束后的可持久化结果。"""

    success: bool
    exit_code: int
    summary: str
    session_id: str | None
    stderr: str = ""
    error_code: str | None = None
    error_message: str | None = None


class CodingAgentAdapter(Protocol):
    """所有 Coding CLI Provider 必须实现的异步协议。"""

    async def probe(self) -> ProbeResult: ...

    def prepare(self, spec: TaskRunSpec) -> PreparedRun: ...

    async def start(self, prepared: PreparedRun) -> RunHandle: ...

    def stream(self, handle: RunHandle) -> AsyncIterator[AdapterEvent]: ...

    async def cancel(self, handle: RunHandle) -> None: ...

    async def collect_result(self, handle: RunHandle) -> AdapterResult: ...

    def resume(self, spec: ResumeSpec) -> PreparedRun: ...

    async def cleanup(self, handle: RunHandle) -> None: ...


class BaseCliAdapter:
    """提供进程生命周期、超时和错误收集的适配器基类。"""

    provider: str

    def __init__(self, process_runner: ProcessRunner) -> None:
        self._process_runner = process_runner

    async def start(self, prepared: PreparedRun) -> RunHandle:
        try:
            process = await self._process_runner.start(
                prepared.command,
                cwd=prepared.cwd,
                environment=prepared.environment,
                stdin=prepared.stdin,
            )
        except (FileNotFoundError, OSError) as exc:
            raise AdapterError(
                "process_start_failed",
                f"无法启动 {self.provider} CLI: {exc}",
            ) from exc
        return RunHandle(
            prepared=prepared,
            process=process,
            session_id=prepared.expected_session_id,
        )

    async def cancel(self, handle: RunHandle) -> None:
        if handle.exit_code is not None:
            return
        handle.cancelled = True
        await handle.process.stop()
        handle.exit_code = await handle.process.wait()

    async def cleanup(self, handle: RunHandle) -> None:
        if handle.exit_code is None:
            await self.cancel(handle)

    async def _probe_command(self, command: tuple[str, ...]) -> tuple[bool, str]:
        try:
            captured = await self._process_runner.capture(
                command,
                timeout_seconds=5.0,
            )
        except (FileNotFoundError, OSError, TimeoutError):
            return False, ""
        output = captured.stdout.strip() or captured.stderr.strip()
        return captured.exit_code == 0, output

    async def _stream_json_events(
        self,
        handle: RunHandle,
        parser: Callable[[Mapping[str, Any]], list[AdapterEvent]],
    ) -> AsyncIterator[AdapterEvent]:
        stderr_task = asyncio.create_task(self._collect_stderr(handle))
        try:
            async with asyncio.timeout(handle.prepared.spec.timeout_seconds):
                async for line in handle.process.stdout_lines():
                    from .stream import decode_json_line

                    raw = decode_json_line(line)
                    if raw is None:
                        continue
                    session_id = raw.get("session_id") or raw.get("thread_id")
                    if isinstance(session_id, str) and session_id:
                        handle.session_id = session_id
                    for event in parser(raw):
                        event_session_id = event.payload.get("session_id")
                        if isinstance(event_session_id, str) and event_session_id:
                            handle.session_id = event_session_id
                        if event.event_type == "adapter_error":
                            handle.error_code = "process_crashed"
                            handle.error_message = str(
                                event.payload.get("message") or "Provider 返回错误事件"
                            )
                        handle.events.append(event)
                        yield event
                handle.exit_code = await handle.process.wait()
        except TimeoutError:
            handle.timed_out = True
            handle.error_code = "process_timeout"
            handle.error_message = (
                f"{self.provider} CLI 超过 "
                f"{handle.prepared.spec.timeout_seconds:g} 秒"
            )
            await handle.process.stop()
            handle.exit_code = await handle.process.wait()
            event = AdapterEvent(
                "adapter_error",
                {"code": handle.error_code, "message": handle.error_message},
            )
            handle.events.append(event)
            yield event
        except AdapterError as exc:
            handle.error_code = exc.code
            handle.error_message = str(exc)
            await handle.process.stop()
            handle.exit_code = await handle.process.wait()
            event = AdapterEvent(
                "adapter_error",
                {"code": exc.code, "message": str(exc)},
            )
            handle.events.append(event)
            yield event
        finally:
            await stderr_task
        exit_event = AdapterEvent(
            "process_exited",
            {
                "exit_code": handle.exit_code,
                "cancelled": handle.cancelled,
                "timed_out": handle.timed_out,
            },
        )
        handle.events.append(exit_event)
        yield exit_event

    async def _collect_stderr(self, handle: RunHandle) -> None:
        chunks: list[str] = []
        async for line in handle.process.stderr_lines():
            chunks.append(line.decode("utf-8", errors="replace"))
        handle.stderr = "".join(chunks)

    async def collect_result(self, handle: RunHandle) -> AdapterResult:
        if handle.exit_code is None:
            raise AdapterError(
                "process_crashed",
                "必须先完整消费 stream() 才能收集运行结果",
                stderr=handle.stderr,
            )
        summary = self._read_summary(handle)
        error_code = handle.error_code
        error_message = handle.error_message
        if handle.cancelled:
            error_code = "cancelled"
            error_message = "运行已取消"
        elif handle.timed_out:
            error_code = "process_timeout"
            error_message = "运行超时"
        elif handle.exit_code != 0:
            error_code = "process_crashed"
            error_message = handle.stderr.strip() or f"CLI 退出码为 {handle.exit_code}"
        result = AdapterResult(
            success=error_code is None,
            exit_code=handle.exit_code,
            summary=summary,
            session_id=handle.session_id,
            stderr=handle.stderr,
            error_code=error_code,
            error_message=error_message,
        )
        handle.events.append(
            AdapterEvent(
                "result_collected",
                {
                    "success": result.success,
                    "exit_code": result.exit_code,
                    "session_id": result.session_id,
                    "error_code": result.error_code,
                },
            )
        )
        return result

    def _read_summary(self, handle: RunHandle) -> str:
        output_file = handle.prepared.output_file
        if output_file is not None and output_file.is_file():
            return output_file.read_text(encoding="utf-8").strip()
        for event in reversed(handle.events):
            if event.event_type == "assistant_delta":
                text = event.payload.get("text")
                if isinstance(text, str):
                    return text.strip()
        return ""
