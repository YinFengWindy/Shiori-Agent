"""Resolves the fixed native components from source or frozen resources."""

from dataclasses import dataclass
from pathlib import Path
import sys

from bootstrap.paths import resource_root


@dataclass(frozen=True)
class BrowserRuntime:
    """Explicit native program locations, injectable without downloading in tests."""

    agent_browser: Path
    chrome: Path

    @classmethod
    def resolve(cls) -> "BrowserRuntime":
        """Finds only Shiori's prepared components, never system browser or npm fallbacks."""
        if sys.platform != "win32":
            raise RuntimeError("Browser Use 首版仅支持 Windows x64")
        root = resource_root() / "native" / "browser-use"
        runtime = cls(root / "agent-browser.exe", root / "chrome-win64" / "chrome.exe")
        for path in (runtime.agent_browser, runtime.chrome):
            if not path.is_file():
                raise FileNotFoundError(
                    f"Browser Use 运行组件缺失：{path}；开发环境请运行 pnpm prepare:browser-use，发行版请重新安装"
                )
        return runtime
