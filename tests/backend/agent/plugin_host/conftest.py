"""plugin_host 测试 fixture：隔离导入命名空间与外部契约包。

内核构造助手位于 ``tests.support.plugin_kernel``。
"""

from __future__ import annotations

from pathlib import Path

import pytest

# 预热 agent.core 导入链，避免 agent.lifecycle.types 触发循环导入
from agent.core.passive_turn import ContextStore as _  # noqa: F401


@pytest.fixture(autouse=True)
def _clean_plugin_modules():
    import sys

    modules_before = set(sys.modules)
    yield
    # 清理测试期间导入的插件模块。
    for name in set(sys.modules) - modules_before:
        if name.startswith("akasic_plugin_"):
            _ = sys.modules.pop(name, None)


@pytest.fixture
def contract_package(tmp_path: Path) -> Path:
    """A tiny external contract package for static validation and kernel gates."""
    package = tmp_path / "external_demo"
    (package / "backend").mkdir(parents=True)
    (package / "renderer").mkdir()
    (package / "manifest.yaml").write_text(
        "api: 4\nsdk: '>=4.0.0 <4.2.0'\nid: external_demo\nversion: 1.2.3\n"
        "entry: backend/plugin.py\n"
        "frontend:\n  entry: renderer/frontend.mjs\n  exports: [ui, background, surface]\n  css: [renderer/style.css]\n"
        "  peers: {react: '>=19.2.0 <20.0.0', react-dom: '>=19.2.0 <20.0.0', '@yinfengwindy/shiori-sdk': '>=4.0.0 <4.2.0'}\n",
        encoding="utf-8",
    )
    (package / "backend/plugin.py").write_text(
        "async def setup(ctx):\n    ctx.expose({'ready': True})\n", encoding="utf-8"
    )
    (package / "renderer/frontend.mjs").write_text(
        'export const ui = {pluginId: "external_demo"}; export const background = {}; export const surface = {};\n',
        encoding="utf-8",
    )
    (package / "renderer/style.css").write_text(".demo {}\n", encoding="utf-8")
    return package
