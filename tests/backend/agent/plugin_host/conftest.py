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
        "api: 2\npackage_contract: 1\nid: external_demo\nversion: 1.2.3\n"
        "runtime_api: '>=3.0.0 <4.0.0'\nentry: backend/plugin.py\n"
        "capabilities: []\n"
        "peer_dependencies: {react: '>=19.2.0 <20.0.0', react-dom: '>=19.2.0 <20.0.0'}\n"
        "renderer:\n  ui: {entry: renderer/ui.mjs, css: [renderer/style.css]}\n"
        "  background: {entry: renderer/background.mjs, css: []}\n"
        "  surface: {entry: renderer/surface.mjs, css: [renderer/style.css]}\n",
        encoding="utf-8",
    )
    (package / "backend/plugin.py").write_text(
        "async def setup(ctx):\n    ctx.expose({'ready': True})\n", encoding="utf-8"
    )
    for name in ("ui", "background", "surface"):
        (package / f"renderer/{name}.mjs").write_text(
            'export default {pluginId: "external_demo"};\n', encoding="utf-8"
        )
    (package / "renderer/style.css").write_text(".demo {}\n", encoding="utf-8")
    return package
