"""受 Codex 外层 sandbox 约束的 Claude Code CLI 适配器。"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

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
from .stream import parse_claude_event

_READ_ONLY_TOOLS = "Read,Glob,Grep"
_WRITE_TOOLS = "Read,Glob,Grep,Edit,Write,Bash,NotebookEdit"
_DISALLOWED_TOOLS = "WebFetch,WebSearch"


class ClaudeAdapter(BaseCliAdapter):
    """启动 Claude stream-json，并强制经过命名外层 sandbox。"""

    provider = "claude"

    def __init__(self, process_runner: ProcessRunner | None = None) -> None:
        super().__init__(process_runner or AsyncioProcessRunner())

    async def probe(self) -> ProbeResult:
        available, version = await self._probe_command(("claude", "--version"))
        if not available:
            return ProbeResult(
                False,
                error="Claude Code CLI 不可用",
                error_code="provider_unavailable",
            )
        cli_available, cli_help = await self._probe_command(("claude", "--help"))
        required_options = (
            "--output-format",
            "--permission-mode",
            "--session-id",
            "--resume",
            "--allowed-tools",
        )
        if not cli_available or any(
            option not in cli_help for option in required_options
        ):
            return ProbeResult(
                False,
                version=version,
                error="Claude Code CLI 缺少 stream-json、session 或权限能力",
                error_code="cli_version_unsupported",
            )
        sandbox_available, _ = await self._probe_command(
            ("codex", "sandbox", "--help")
        )
        if not sandbox_available:
            return ProbeResult(
                False,
                version=version,
                error="Claude Code 所需的 Codex sandbox runner 不可用",
                error_code="sandbox_unavailable",
            )
        return ProbeResult(True, version=version, sandbox_available=True)

    def prepare(self, spec: TaskRunSpec) -> PreparedRun:
        return self._prepare(spec, resume_session_id=None)

    def resume(self, spec: ResumeSpec) -> PreparedRun:
        session_id = validate_session_id(spec.session_id, "Claude")
        return self._prepare(spec.run, resume_session_id=session_id)

    def _prepare(
        self,
        spec: TaskRunSpec,
        *,
        resume_session_id: str | None,
    ) -> PreparedRun:
        permission = self._validate_spec(spec)
        expected_session_id = resume_session_id or str(uuid.uuid4())
        inner = self._inner_command(
            spec,
            permission=permission,
            session_id=expected_session_id,
            is_resume=resume_session_id is not None,
        )
        command = (
            "codex",
            "sandbox",
            "-P",
            spec.sandbox_profile or "",
            "-C",
            str(spec.worktree),
            "--",
            *inner,
        )
        return PreparedRun(
            spec=spec,
            command=command,
            cwd=spec.worktree,
            stdin=(spec.task + "\n").encode("utf-8"),
            environment=dict(spec.environment),
            expected_session_id=expected_session_id,
        )

    def stream(self, handle: RunHandle) -> AsyncIterator[AdapterEvent]:
        return self._stream_json_events(handle, parse_claude_event)

    def _inner_command(
        self,
        spec: TaskRunSpec,
        *,
        permission: PermissionLevel,
        session_id: str,
        is_resume: bool,
    ) -> tuple[str, ...]:
        tools = (
            _READ_ONLY_TOOLS
            if permission is PermissionLevel.READ_ONLY
            else _WRITE_TOOLS
        )
        permission_mode = (
            "plan" if permission is PermissionLevel.READ_ONLY else "dontAsk"
        )
        command = [
            "claude",
            "--print",
            "--output-format",
            "stream-json",
            "--include-partial-messages",
            "--verbose",
            "--model",
            spec.model,
            "--effort",
            spec.effort,
            "--permission-mode",
            permission_mode,
            "--allowed-tools",
            tools,
            "--disallowed-tools",
            _DISALLOWED_TOOLS,
            "--disable-slash-commands",
            "--no-chrome",
            "--safe-mode",
            "--strict-mcp-config",
            "--mcp-config",
            "{}",
            "--setting-sources",
            "user",
        ]
        if spec.max_budget_usd is not None:
            command.extend(("--max-budget-usd", str(spec.max_budget_usd)))
        if is_resume:
            command.extend(("--resume", session_id))
        else:
            command.extend(("--session-id", session_id))
        return tuple(command)

    def _validate_spec(self, spec: TaskRunSpec) -> PermissionLevel:
        try:
            permission = PermissionLevel(spec.permission_level)
        except ValueError as exc:
            raise AdapterError(
                "unsupported_capability",
                f"Claude 不支持权限档位 {spec.permission_level!r}",
            ) from exc
        if not spec.sandbox_profile:
            raise AdapterError(
                "sandbox_unavailable",
                "Claude Code 必须配置外层 Codex sandbox profile",
            )
        if spec.timeout_seconds <= 0:
            raise AdapterError("unsupported_capability", "运行超时必须大于 0")
        if spec.max_budget_usd is not None and spec.max_budget_usd <= 0:
            raise AdapterError("unsupported_capability", "Claude 预算必须大于 0")
        if not spec.worktree.is_absolute():
            raise AdapterError("path_boundary_violation", "worktree 必须是绝对路径")
        return permission
