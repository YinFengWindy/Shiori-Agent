"""The core's minimal shell guard refuses only whole-disk, home and workspace wipes."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent.tools.shell.guard import destructive_command_reason

WORKSPACE = Path("/srv/shiori/workspace").resolve()


@pytest.mark.parametrize(
    "command",
    [
        # 1. 删除根目录、驱动器根、用户主目录或工作区根
        "rm -rf /",
        "rm -rf /*",
        "sudo rm -rf --no-preserve-root /",
        "rm -fr /tmp/..",
        "rm -rf ~",
        "rm -rf ~/",
        'rm -rf "$HOME"/*',
        f"rm -rf {Path.home()}",
        f"rm -rf {WORKSPACE}/",
        "cd /tmp && rm -rf /",
        "ls\nrm -rf ~",
        "echo $(rm -rf /)",
        "bash -c 'rm -rf ~'",
        "Remove-Item -Recurse -Force C:\\",
        "Remove-Item -Path:C:\\* -Recurse",
        "rm -r -fo $env:USERPROFILE",
        # 2. 写块设备
        "dd if=/dev/zero of=/dev/sda bs=1M",
        "cat image.iso > /dev/nvme0n1",
        "mkfs.ext4 /dev/sdb1",
        # 3. 格式化磁盘
        "Format-Volume -DriveLetter D",
        "Get-Disk 1 | Clear-Disk -RemoveData",
        "format D: /q",
    ],
)
def test_catastrophic_commands_are_refused(command: str) -> None:
    assert destructive_command_reason(command, protected_dirs=[WORKSPACE])


@pytest.mark.parametrize(
    "command",
    [
        "rm notes.txt",
        "rm -rf build/",
        "rm -rf ./node_modules dist",
        "rm -rf /tmp/shiori-test",
        "rm -rf ~/.cache/pip",
        'rm -rf "$HOME/.cache"',
        f"rm -rf {WORKSPACE}/sessions/tmp",
        "rm -rf *",
        "git rm -r --cached .",
        "find . -name '*.pyc' -delete",
        "Remove-Item -Recurse -Force .\\dist",
        "ls / && du -sh ~",
        "dd if=/dev/zero of=disk.img bs=1M count=10",
        "dd if=/dev/sda of=backup.img",
        "echo hi > /dev/null",
        "mkfs.ext4 disk.img",
        "Get-Process | Format-Table",
        "echo 'rm -rf /'",
        "rm 'unbalanced",
    ],
)
def test_ordinary_commands_pass(command: str) -> None:
    assert destructive_command_reason(command, protected_dirs=[WORKSPACE]) is None
