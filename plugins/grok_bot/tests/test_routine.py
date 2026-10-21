from pathlib import PurePosixPath, PureWindowsPath
from plugins.grok_bot.backend.routine import routine_config


def test_windows_instructions_quote_actual_paths_and_pipe_into_a_new_process():
    text = routine_config(
        PureWindowsPath("C:/O'Brien/插件/client.ps1"),
        PureWindowsPath("C:/data/角色/client.json"),
    )
    assert r"$callbackClient = 'C:\O''Brien\插件\client.ps1'" in text
    assert r"$connectionFile = 'C:\data\角色\client.json'" in text
    assert "$payloadJson | & powershell.exe" in text
    assert "-Handshake" not in text
    assert "connection_check" not in text
    assert "回复必须用 reply_to" in text
    assert "真正主动发起的新交流才省略 reply_to" in text


def test_python_instructions_supply_both_local_paths_and_utf8_stdin():
    text = routine_config(
        PurePosixPath("/app/my plugin/client.py"),
        PurePosixPath("/data/my role/client.json"),
    )
    assert (
        "python3 '/app/my plugin/client.py' --connection '/data/my role/client.json'"
        in text
    )
    assert "UTF-8 JSON" in text
    assert "--handshake" not in text
