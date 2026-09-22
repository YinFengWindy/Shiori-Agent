from __future__ import annotations

import pytest

from agent.tools.shell import validation
from agent.tools.shell import _validate_network_command


def test_validate_network_command_rejects_non_http_url():
    assert "URL" in (_validate_network_command("curl ftp://x") or "")


def test_validate_network_command_rejects_upload_and_file_writes():
    assert "上传/写文件" in (
        _validate_network_command("curl -o out http://x.com") or ""
    )


def test_validate_network_command_rejects_intranet_targets():
    assert "禁止访问内网" in (_validate_network_command("curl http://127.0.0.1") or "")


def test_validate_network_command_allows_non_network_command():
    assert _validate_network_command("echo hi") is None


@pytest.mark.parametrize(
    "command",
    [
        'Write-Output "it\'s valid"',
        'Write-Output "quoted `"text`""',
        "Write-Output 'it''s valid'",
        'Write-Output @"\na here-string with \' and "\n"@',
        "Write-Output first; Write-Output second\nWrite-Output third",
    ],
)
def test_windows_unrestricted_scripts_are_parsed_by_powershell(monkeypatch, command):
    monkeypatch.setattr(validation, "_IS_WINDOWS", True)
    assert (
        validation._validate_command(command, allow_network=True, restricted_dir=None)
        is None
    )


@pytest.mark.parametrize(
    "command",
    [
        "Get-Item $env:USERPROFILE",
        "Get-Item (Join-Path C: secret)",
        "Get-Item .\nGet-Item ../secret",
        "Get-Item `\n../secret",
        "& { Get-Item ../secret }",
        "Get-Item @paths",
        "pwsh -Command Get-Item",
        "powershell.exe -Command Get-Item",
        "cmd /c dir",
        "iex 'Get-Item ../secret'",
        "Start-Process cmd.exe",
        r"C:\Windows\System32\cmd.exe /c dir",
        "Get-Item -LiteralPath:../secret",
        r"Get-Item -Path:C:\Windows\secret",
        r'Get-Item -LiteralPath:"C:\Program Files\secret"',
        "Get-Item 'a','../secret'",
    ],
)
def test_windows_restricted_commands_reject_dynamic_syntax_and_shells(
    monkeypatch, tmp_path, command
):
    monkeypatch.setattr(validation, "_IS_WINDOWS", True)
    assert validation._validate_command(
        command, allow_network=False, restricted_dir=tmp_path, cwd=tmp_path
    )


@pytest.mark.parametrize(
    "command", ["Invoke-WebRequest", "iwr", "Invoke-RestMethod", "irm", "curl.exe"]
)
def test_windows_network_commands_respect_disabled_network(monkeypatch, command):
    monkeypatch.setattr(validation, "_IS_WINDOWS", True)
    assert "禁止网络访问" in (
        validation._validate_command(
            f"{command} https://example.com", allow_network=False, restricted_dir=None
        )
        or ""
    )


def test_windows_attached_parameter_allows_relative_path(monkeypatch, tmp_path):
    monkeypatch.setattr(validation, "_IS_WINDOWS", True)
    assert (
        validation._validate_command(
            "Get-Item -LiteralPath:logs/output.txt",
            allow_network=False,
            restricted_dir=tmp_path,
            cwd=tmp_path,
        )
        is None
    )
