"""A failed native termination cannot be mistaken for released process ownership."""

import asyncio
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from shiori_sdk.managed import child as child_module
from shiori_sdk.managed.child import OwnedChild, run_owned
from shiori_sdk.managed.paths import native_path
from shiori_sdk.testing.processes import FakeProcesses


async def test_close_failure_keeps_handles_until_exit_can_be_joined(
    tmp_path, monkeypatch
):
    child = OwnedChild(FakeProcesses())
    process = SimpleNamespace(returncode=None, wait=AsyncMock(return_value=0))

    class Owner:
        fail = True

        def close(self):
            if self.fail:
                raise OSError("native close failed")

    owner = Owner()
    monkeypatch.setattr(child, "process", process)
    child.owner = owner
    child.log = (tmp_path / "child.log").open("a", encoding="utf-8")
    with pytest.raises(OSError, match="native close failed"):
        await child.close()
    assert child.process is process and child.owner is owner
    assert not child.log.closed
    process.wait.assert_not_awaited()
    owner.fail = False
    await child.close()
    process.wait.assert_awaited_once()
    assert child.process is None and child.owner is None and child.log is None


@pytest.mark.parametrize("extended", [False, True])
async def test_spawn_preserves_callers_interpreter_and_working_directory(
    tmp_path, monkeypatch, extended
):
    processes = FakeProcesses()
    received = {}
    process = SimpleNamespace(returncode=0, wait=AsyncMock(return_value=0), stdout=None)

    async def spawn(*command, **kwargs):
        received.update(command=command, **kwargs)
        return process, None

    monkeypatch.setattr(processes, "spawn", spawn)
    child = OwnedChild(processes)
    interpreter = tmp_path / "private environment/python.exe"
    if extended:
        interpreter, tmp_path = native_path(interpreter), native_path(tmp_path)
    await child.start(
        [str(interpreter), "-I", "server.py"],
        cwd=tmp_path,
        env={},
        log=tmp_path / "child.log",
    )
    assert received["command"] == (str(interpreter), "-I", "server.py")
    assert received["cwd"] == str(tmp_path)
    await child.close()


async def test_system_code_page_output_is_logged_as_utf8_and_names_the_failure(
    tmp_path, monkeypatch
):
    # The tail 7-Zip wrote on a full disk under Chinese Windows (GBK bytes).
    full = "磁盘空间不足。".encode("gbk")
    output = (
        b"ERROR: Cannot set length for output file : " + full + b" : s2G.pth\r\n"
        b"\r\nSub items Errors: 1\r\n\r\nSystem ERROR:\r\n" + full + b"\r\n"
    )
    processes = FakeProcesses()

    async def spawn(*command, **kwargs):
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            "import sys; sys.stdout.buffer.write(bytes.fromhex(sys.argv[1])); "
            "sys.exit(2)",
            output.hex(),
            **(kwargs | {"env": None}),
        )
        return process, None

    monkeypatch.setattr(processes, "spawn", spawn)
    monkeypatch.setattr(child_module, "_system_encoding", lambda: "gbk")
    log = tmp_path / "prepare.log"
    with pytest.raises(RuntimeError) as failure:
        await run_owned(processes, ["7zr.exe"], cwd=tmp_path, env={}, log=log)
    assert str(failure.value).startswith(
        "环境准备命令失败（2）：System ERROR: 磁盘空间不足。详见 "
    )
    text = log.read_text(encoding="utf-8")
    assert "Cannot set length for output file : 磁盘空间不足。 : s2G.pth\n" in text
