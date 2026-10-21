import asyncio
import json
import shutil
import subprocess
from pathlib import Path

import pytest
from plugins.grok_bot.backend.client import submit


async def test_python_client_reads_credentials_and_supports_unicode_multiline(harness):
    connection = harness.connection
    payload = {"message_id": "client-1", "text": "你好\n第二行"}
    result = await asyncio.to_thread(submit, connection.client_file, payload)
    assert result == {"status": "accepted", "message_id": "client-1"}
    assert harness.bus.inbound[0].content == payload["text"]


async def test_windows_powershell_client_runs_without_python_or_sdk(harness):
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if powershell is None:
        pytest.skip("Windows PowerShell is not installed on this platform")
    connection = harness.connection
    script = Path(__file__).resolve().parents[1] / "client.ps1"

    def invoke(*arguments, payload=""):
        return subprocess.run(
            [
                powershell,
                "-NoProfile",
                "-NonInteractive",
                "-File",
                str(script),
                "-Connection",
                str(connection.client_file),
                *arguments,
            ],
            input=payload,
            text=True,
            encoding="utf-8",
            capture_output=True,
            timeout=25,
            check=False,
        )

    result = await asyncio.to_thread(
        invoke,
        payload=json.dumps(
            {"message_id": "ps-1", "text": "你好\n第二行"}, ensure_ascii=False
        ),
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["status"] == "accepted"
    assert harness.bus.inbound[-1].content == "你好\n第二行"
    assert connection.config.callback_token not in result.stdout + result.stderr
