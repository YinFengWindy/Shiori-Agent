from __future__ import annotations

from pathlib import Path

import pytest

from coding_agents.adapters.base import AdapterError, ResumeSpec, TaskRunSpec
from coding_agents.adapters.codex import CodexAdapter
from coding_agents.adapters.process import CapturedProcess

from .conftest import FakeProcess, FakeProcessRunner


def _spec(tmp_path: Path, permission: str = "workspace-write") -> TaskRunSpec:
    return TaskRunSpec(
        run_id="run-codex",
        task="实现功能",
        worktree=tmp_path,
        model="gpt-test",
        effort="high",
        permission_level=permission,
        timeout_seconds=30,
        environment={"PATH": "bin"},
        sandbox_profile="approved-run",
    )


def test_workspace_write_uses_native_codex_sandbox(tmp_path: Path) -> None:
    prepared = CodexAdapter(FakeProcessRunner()).prepare(_spec(tmp_path))

    assert prepared.command[:2] == ("codex", "exec")
    sandbox = prepared.command[prepared.command.index("--sandbox") + 1]
    assert sandbox == "workspace-write"
    assert "--dangerously-bypass-approvals-and-sandbox" not in prepared.command
    assert prepared.stdin == "实现功能\n".encode()


def test_full_access_is_wrapped_by_managed_outer_sandbox(tmp_path: Path) -> None:
    prepared = CodexAdapter(FakeProcessRunner()).prepare(
        _spec(tmp_path, "full-access")
    )

    assert prepared.command[:6] == (
        "codex",
        "sandbox",
        "-P",
        "approved-run",
        "-C",
        str(tmp_path),
    )
    assert "danger-full-access" in prepared.command
    assert "--dangerously-bypass-approvals-and-sandbox" not in prepared.command


def test_full_access_without_outer_profile_fails(tmp_path: Path) -> None:
    spec = _spec(tmp_path, "full-access")
    spec = TaskRunSpec(**{**spec.__dict__, "sandbox_profile": None})

    with pytest.raises(AdapterError) as raised:
        CodexAdapter(FakeProcessRunner()).prepare(spec)

    assert raised.value.code == "sandbox_unavailable"


def test_output_file_outside_worktree_fails(tmp_path: Path) -> None:
    spec = _spec(tmp_path)
    spec = TaskRunSpec(**{**spec.__dict__, "output_file": tmp_path.parent / "out.txt"})

    with pytest.raises(AdapterError) as raised:
        CodexAdapter(FakeProcessRunner()).prepare(spec)

    assert raised.value.code == "path_boundary_violation"


def test_resume_uses_explicit_session_and_never_last(tmp_path: Path) -> None:
    prepared = CodexAdapter(FakeProcessRunner()).resume(
        ResumeSpec(_spec(tmp_path), "session-123")
    )

    assert "resume" in prepared.command
    assert "session-123" in prepared.command
    assert "--last" not in prepared.command


@pytest.mark.parametrize(
    "session_id",
    ["", "--last", "-x", "session id", "session\nid", " session-123"],
)
def test_resume_rejects_unsafe_session_ids(
    tmp_path: Path,
    session_id: str,
) -> None:
    with pytest.raises(AdapterError) as raised:
        CodexAdapter(FakeProcessRunner()).resume(
            ResumeSpec(_spec(tmp_path), session_id)
        )

    assert raised.value.code == "session_unrecoverable"


@pytest.mark.asyncio
async def test_probe_and_stream_capture_version_and_session(tmp_path: Path) -> None:
    process = FakeProcess(
        stdout=(
            b'{"type":"thread.started","thread_id":"thread-1"}\n',
            (
                '{"type":"item.completed","item":'
                '{"type":"agent_message","text":"完成"}}\n'
            ).encode(),
        )
    )
    runner = FakeProcessRunner(
        process,
        captures=(
            CapturedProcess(0, "codex-cli 1.2.3\n", ""),
            CapturedProcess(
                0,
                "--json --output-last-message --sandbox",
                "",
            ),
            CapturedProcess(0, "sandbox help", ""),
        ),
    )
    adapter = CodexAdapter(runner)

    probe = await adapter.probe()
    handle = await adapter.start(adapter.prepare(_spec(tmp_path)))
    events = [event async for event in adapter.stream(handle)]
    result = await adapter.collect_result(handle)

    assert probe.version == "codex-cli 1.2.3"
    assert probe.sandbox_available is True
    assert handle.session_id == "thread-1"
    assert result.summary == "完成"
    assert events[-1].event_type == "process_exited"


@pytest.mark.asyncio
async def test_probe_rejects_cli_without_required_capabilities() -> None:
    runner = FakeProcessRunner(
        captures=(
            CapturedProcess(0, "codex-cli 0.1", ""),
            CapturedProcess(0, "old help", ""),
        )
    )

    result = await CodexAdapter(runner).probe()

    assert result.available is False
    assert result.error_code == "cli_version_unsupported"
