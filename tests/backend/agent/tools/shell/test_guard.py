"""The core's minimal shell guard refuses only whole-disk, home and workspace wipes."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent.tools.shell.guard import destructive_command_reason

WORKSPACE = Path("/srv/shiori/workspace").resolve()


@pytest.mark.parametrize(
    "command",
    [
        "rm -rf /",  # 根目录
        "rm -rf ~",  # 用户主目录
        f"rm -rf {WORKSPACE.as_posix()}/",  # 工作区根
        "rm -rf /*",  # 目录下的全部内容
        "ls\nrm -rf ~",  # 换行分出的第二条命令
        "echo $(rm -rf /)",  # 命令替换
        "bash -c 'rm -rf ~'",  # sh 包装
        "pwsh -Command 'Remove-Item -Recurse ~'",  # PowerShell 包装
        'cmd /c "rd /s /q C:\\"',  # cmd 包装，驱动器根
        "mv ~ /tmp/elsewhere",  # 整个移走
        "dd if=/dev/zero of=/dev/sda bs=1M",  # 写块设备
        "mkfs.ext4 /dev/sdb1",  # 在块设备上建文件系统
        "format D: /q",  # 格式化盘符
    ],
)
def test_catastrophic_commands_are_refused(command: str) -> None:
    assert destructive_command_reason(command, protected_dirs=[WORKSPACE])


@pytest.mark.parametrize(
    "command",
    [
        "rm -rf build/",
        "rm -rf ~/.cache/pip",
        "dd if=/dev/zero of=disk.img bs=1M count=10",
        "echo 'rm -rf /'",
    ],
)
def test_ordinary_commands_pass(command: str) -> None:
    assert destructive_command_reason(command, protected_dirs=[WORKSPACE]) is None
