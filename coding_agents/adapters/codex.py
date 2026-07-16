"""Codex CLI 的非交互 JSONL 适配器。"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from pathlib import Path

from coding_agents.models import PermissionLevel

from .base import (
    AdapterError,
    AdapterEvent,
    BaseCliAdapter,
    PreparedRun,
    ProbeResult,
    ResumeSpec,
    RunHandle,
    TaskRunSpec,
    validate_session_id,
)
from .process import AsyncioProcessRunner, ProcessRunner
from .stream import parse_codex_event

class CodexAdapter(BaseCliAdapter):
    """以参数数组启动并恢复 Codex exec 会话。"""

    provider = "codex"

    def __init__(self, process_runner: ProcessRunner | None = None) -> None:
        super().__init__(process_runner or AsyncioProcessRunner())

    async def probe(self) -> ProbeResult:
        available, version = await self._probe_command(("codex", "--version"))
        if not available:
            return ProbeResult(
                False,
                error="Codex CLI 不可用",
                error_code="provider_unavailable",
            )
        exec_available, exec_help = await self._probe_command(
            ("codex", "exec", "--help")
        )
        required_options = ("--json", "--output-last-message", "--sandbox")
        if not exec_available or any(
            option not in exec_help for option in required_options
        ):
            return ProbeResult(
                False,
                version=version,
                error="Codex CLI 缺少 JSONL、结果文件或 sandbox 能力",
                error_code="cli_version_unsupported",
            )
        sandbox_available, _ = await self._probe_command(
            ("codex", "sandbox", "--help")
        )
        return ProbeResult(
            True,
            version=version,
            sandbox_available=sandbox_available,
        )

    def prepare(self, spec: TaskRunSpec) -> PreparedRun:
        return self._prepare(spec, session_id=None)

    def resume(self, spec: ResumeSpec) -> PreparedRun:
        session_id = validate_session_id(spec.session_id, "Codex")
        return self._prepare(spec.run, session_id=session_id)

    def _prepare(self, spec: TaskRunSpec, session_id: str | None) -> PreparedRun:
        permission = self._validate_spec(spec)
        output_file = spec.output_file or self._default_output_file(spec)
        self._validate_output_file(spec.worktree, output_file)
        inner = self._inner_command(
            spec,
            output_file,
            permission=permission,
            session_id=session_id,
        )
        command = self._wrap_full_access(spec, inner, permission=permission)
        return PreparedRun(
            spec=spec,
            command=tuple(command),
            cwd=spec.worktree,
            stdin=(spec.task + "\n").encode("utf-8"),
            environment=dict(spec.environment),
            output_file=output_file,
            expected_session_id=session_id,
        )

    def stream(self, handle: RunHandle) -> AsyncIterator[AdapterEvent]:
        return self._stream_json_events(handle, parse_codex_event)

    def _inner_command(
        self,
        spec: TaskRunSpec,
        output_file: Path,
        *,
        permission: PermissionLevel,
        session_id: str | None,
    ) -> list[str]:
        sandbox = (
            "danger-full-access"
            if permission is PermissionLevel.FULL_ACCESS
            else permission.value
        )
        command = [
            "codex",
            "exec",
            "-C",
            str(spec.worktree),
            "--model",
            spec.model,
            "--sandbox",
            sandbox,
            "--json",
            "--output-last-message",
            str(output_file),
            "--color",
            "never",
            "-c",
            'approval_policy="never"',
            "-c",
            f'model_reasoning_effort="{spec.effort}"',
        ]
        if session_id is not None:
            command.extend(("resume", session_id, "-"))
        else:
            command.append("-")
        return command

    def _wrap_full_access(
        self,
        spec: TaskRunSpec,
        inner: list[str],
        *,
        permission: PermissionLevel,
    ) -> list[str]:
        if permission is not PermissionLevel.FULL_ACCESS:
            return inner
        if not spec.sandbox_profile:
            raise AdapterError(
                "sandbox_unavailable",
                "Codex full-access 必须配置外层 sandbox profile",
            )
        return [
            "codex",
            "sandbox",
            "-P",
            spec.sandbox_profile,
            "-C",
            str(spec.worktree),
            "--",
            *inner,
        ]

    def _validate_spec(self, spec: TaskRunSpec) -> PermissionLevel:
        try:
            permission = PermissionLevel(spec.permission_level)
        except ValueError as exc:
            raise AdapterError(
                "unsupported_capability",
                f"Codex 不支持权限档位 {spec.permission_level!r}",
            ) from exc
        if spec.timeout_seconds <= 0:
            raise AdapterError("unsupported_capability", "运行超时必须大于 0")
        if not spec.worktree.is_absolute():
            raise AdapterError("path_boundary_violation", "worktree 必须是绝对路径")
        return permission

    @staticmethod
    def _validate_output_file(worktree: Path, output_file: Path) -> None:
        try:
            output_file.resolve().relative_to(worktree.resolve())
        except ValueError as exc:
            raise AdapterError(
                "path_boundary_violation",
                "Codex 结果文件必须位于受管 worktree 内",
            ) from exc

    @staticmethod
    def _default_output_file(spec: TaskRunSpec) -> Path:
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", spec.run_id) is None:
            raise AdapterError("path_boundary_violation", "Run ID 不是安全文件标识")
        return spec.worktree / f".shiori-coding-agent-{spec.run_id}.txt"
