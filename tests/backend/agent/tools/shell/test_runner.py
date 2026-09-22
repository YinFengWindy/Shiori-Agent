from __future__ import annotations

import asyncio
import base64
import os
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from agent.tools.shell import runner


@pytest.mark.asyncio
async def test_windows_launcher_preserves_script_and_process_options(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(runner, "_IS_WINDOWS", True)
    monkeypatch.setattr(
        runner.subprocess, "CREATE_NEW_PROCESS_GROUP", 512, raising=False
    )
    monkeypatch.setattr(runner.shutil, "which", lambda name, path: "C:/pwsh.exe")
    spawn = AsyncMock()
    monkeypatch.setattr(runner.asyncio, "create_subprocess_exec", spawn)
    command = "Write-Output \"中文 `\"quote`\"\"; Write-Output 'it''s literal'\nexit 7"

    await runner._start_process(command, cwd=tmp_path, env={"PATH": "tools"})

    args = spawn.call_args.args
    assert args[:-1] == (
        "C:/pwsh.exe",
        "-NoLogo",
        "-NoProfile",
        "-NonInteractive",
        "-OutputFormat",
        "Text",
        "-EncodedCommand",
    )
    script = base64.b64decode(args[-1]).decode("utf-16-le")
    assert script.endswith("\n" + command)
    assert "[Console]::OutputEncoding" in script
    assert "$OutputEncoding" in script
    assert spawn.call_args.kwargs == {
        "cwd": str(tmp_path),
        "env": {"PATH": "tools"},
        "stdout": asyncio.subprocess.PIPE,
        "stderr": asyncio.subprocess.PIPE,
        "creationflags": 512,
    }


@pytest.mark.asyncio
async def test_posix_launcher_retains_default_shell(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "_IS_WINDOWS", False)
    spawn = AsyncMock()
    monkeypatch.setattr(runner.asyncio, "create_subprocess_shell", spawn)
    await runner._start_process("printf ok", cwd=tmp_path, env={"PATH": "/bin"})
    spawn.assert_awaited_once_with(
        "printf ok",
        cwd=str(tmp_path),
        env={"PATH": "/bin"},
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )


@pytest.mark.asyncio
async def test_windows_launcher_requires_pwsh_from_effective_path(monkeypatch):
    monkeypatch.setattr(runner, "_IS_WINDOWS", True)
    monkeypatch.setattr(
        runner.subprocess, "CREATE_NEW_PROCESS_GROUP", 512, raising=False
    )
    paths = []
    monkeypatch.setattr(runner.shutil, "which", lambda name, path: paths.append(path))
    spawn = AsyncMock()
    monkeypatch.setattr(runner.asyncio, "create_subprocess_exec", spawn)
    with pytest.raises(FileNotFoundError, match="PowerShell 7.*PATH"):
        await runner._start_process("echo ok", env={"PATH": "custom-path"})
    assert paths == ["custom-path"]
    spawn.assert_not_called()


@pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell integration")
@pytest.mark.asyncio
async def test_run_executes_powershell_multiline_unicode_quotes_and_exit(
    tmp_path: Path,
):
    chunks = []
    stdout, stderr, code, interrupted = await runner._run(
        "Write-Output '你好'; Write-Output 'it''s literal'\n"
        'Write-Output "quoted `"text`""\n'
        "[Console]::Error.WriteLine('错误')\nexit 7",
        10,
        cwd=tmp_path,
        on_data=chunks.append,
    )
    assert stdout.splitlines() == ["你好", "it's literal", 'quoted "text"']
    assert stderr.strip() == "错误"
    assert code == 7
    assert not interrupted
    assert "你好" in "".join(chunks)


@pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell integration")
@pytest.mark.asyncio
async def test_run_returns_native_failure_and_readable_errors():
    _, _, code, _ = await runner._run("cmd /c exit 9", 10)
    assert code != 0
    _, stderr, code, _ = await runner._run("throw '失败'", 10)
    assert code != 0
    assert "失败" in stderr
    assert "CLIXML" not in stderr


@pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell integration")
@pytest.mark.asyncio
async def test_run_times_out_powershell():
    _, _, code, interrupted = await runner._run("Start-Sleep -Seconds 60", 1)
    assert code == -1
    assert interrupted
