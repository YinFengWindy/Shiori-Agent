from __future__ import annotations

from pathlib import Path

import pytest

from coding_agents.adapters.base import AdapterError, ResumeSpec, TaskRunSpec
from coding_agents.adapters.claude import ClaudeAdapter
from coding_agents.adapters.process import CapturedProcess

from .conftest import FakeProcess, FakeProcessRunner


def _spec(tmp_path: Path, permission: str = "workspace-write") -> TaskRunSpec:
    return TaskRunSpec(
        run_id="run-claude",
        task="实现功能",
        worktree=tmp_path,
        model="sonnet",
        effort="medium",
        permission_level=permission,
        timeout_seconds=30,
        environment={"PATH": "bin"},
        sandbox_profile="approved-run",
        max_budget_usd=5,
    )


@pytest.mark.parametrize("permission", ["workspace-write", "full-access"])
def test_writing_permissions_always_use_outer_codex_sandbox(
    tmp_path: Path,
    permission: str,
) -> None:
    prepared = ClaudeAdapter(FakeProcessRunner()).prepare(
        _spec(tmp_path, permission)
    )

    assert prepared.command[:6] == (
        "codex",
        "sandbox",
        "-P",
        "approved-run",
        "-C",
        str(tmp_path),
    )
    assert "claude" in prepared.command
    assert "--dangerously-skip-permissions" not in prepared.command
    assert "bypassPermissions" not in prepared.command
    permission_mode = prepared.command[
        prepared.command.index("--permission-mode") + 1
    ]
    assert permission_mode == "dontAsk"


def test_read_only_removes_write_and_shell_tools(tmp_path: Path) -> None:
    prepared = ClaudeAdapter(FakeProcessRunner()).prepare(
        _spec(tmp_path, "read-only")
    )
    allowed = prepared.command[prepared.command.index("--allowed-tools") + 1]

    assert allowed == "Read,Glob,Grep"
    assert prepared.command[prepared.command.index("--permission-mode") + 1] == "plan"


def test_missing_outer_profile_fails_closed(tmp_path: Path) -> None:
    spec = _spec(tmp_path)
    spec = TaskRunSpec(**{**spec.__dict__, "sandbox_profile": None})

    with pytest.raises(AdapterError) as raised:
        ClaudeAdapter(FakeProcessRunner()).prepare(spec)

    assert raised.value.code == "sandbox_unavailable"


def test_resume_uses_explicit_session_id(tmp_path: Path) -> None:
    prepared = ClaudeAdapter(FakeProcessRunner()).resume(
        ResumeSpec(_spec(tmp_path), "session-claude")
    )

    assert prepared.command[prepared.command.index("--resume") + 1] == "session-claude"
    assert "--session-id" not in prepared.command


@pytest.mark.parametrize(
    "session_id",
    ["", "--last", "-x", "session id", "session\nid", "session-123 "],
)
def test_resume_rejects_unsafe_session_ids(
    tmp_path: Path,
    session_id: str,
) -> None:
    with pytest.raises(AdapterError) as raised:
        ClaudeAdapter(FakeProcessRunner()).resume(
            ResumeSpec(_spec(tmp_path), session_id)
        )

    assert raised.value.code == "session_unrecoverable"


@pytest.mark.asyncio
async def test_probe_fails_if_outer_sandbox_is_unavailable() -> None:
    runner = FakeProcessRunner(
        captures=(
            CapturedProcess(0, "2.1.0", ""),
            CapturedProcess(
                0,
                (
                    "--output-format --permission-mode --session-id "
                    "--resume --allowed-tools"
                ),
                "",
            ),
            FileNotFoundError("codex"),
        )
    )

    result = await ClaudeAdapter(runner).probe()

    assert result.available is False
    assert result.version == "2.1.0"
    assert "sandbox" in (result.error or "")


@pytest.mark.asyncio
async def test_stream_extracts_claude_session_and_result(tmp_path: Path) -> None:
    process = FakeProcess(
        stdout=(
            (
                '{"type":"system","subtype":"init",'
                '"session_id":"claude-1"}\n'
            ).encode(),
            (
                '{"type":"result","subtype":"success",'
                '"is_error":false,"result":"完成"}\n'
            ).encode(),
        )
    )
    adapter = ClaudeAdapter(FakeProcessRunner(process))
    handle = await adapter.start(adapter.prepare(_spec(tmp_path)))

    _ = [event async for event in adapter.stream(handle)]
    result = await adapter.collect_result(handle)

    assert result.success is True
    assert result.session_id == "claude-1"
    assert result.summary == "完成"
