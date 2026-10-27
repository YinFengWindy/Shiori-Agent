"""Discover the user-installed ego client without installing or upgrading it."""

from dataclasses import dataclass
from pathlib import Path
import shutil
import sys


@dataclass(frozen=True)
class EgoRuntime:
    """The external client; its GUI and embedded runtime belong to the user."""

    executable: Path

    @classmethod
    def resolve(cls, configured_path: str = "") -> "EgoRuntime":
        """Resolve explicit configuration, PATH, or ego's Windows install location."""
        if sys.platform != "win32":
            raise RuntimeError("Browser Use 首版仅支持 Windows x64")
        if configured_path.strip():
            candidate = Path(configured_path).expanduser()
        else:
            command = shutil.which("ego-browser.exe")
            candidate = (
                Path(command)
                if command
                else Path.home() / ".local/share/ego/active_version_dir/ego-browser.exe"
            )
        if not candidate.is_file() or candidate.suffix.lower() != ".exe":
            raise FileNotFoundError(
                "未找到 ego-browser.exe；请安装并打开 ego(lite)，完成首次设置，"
                "或在插件设置中填写 ego-browser 路径"
            )
        return cls(candidate.resolve())
