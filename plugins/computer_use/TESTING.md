# Computer Use tests

在仓库根使用当前 checkout 的环境：

```powershell
.venv\Scripts\pytest.exe plugins/computer_use/tests tests/backend/agent/mcp tests/backend/agent/tools/test_turn_scope.py tests/backend/agent/test_tool_runtime.py tests/backend/agent/core/passive_turn/test_reasoner.py tests/backend/agent/core/passive_turn/test_reasoning_loop.py tests/backend/proactive_v2/test_mcp_sources_async.py
node --test apps/desktop/scripts/browser-runtime.test.mjs apps/desktop/scripts/computer-runtime.test.mjs apps/desktop/scripts/verify-packaged.test.mjs
```

默认测试使用注入的驱动边界；Windows 还验证真实 OS 独占锁。真实窗口验收需显式开启，只创建并操作自有 WinForms 窗口：

```powershell
pnpm prepare:computer-use
$env:SHIORI_COMPUTER_USE_RUNTIME = (Resolve-Path native/computer-use).Path
$env:SHIORI_COMPUTER_USE_EVIDENCE = (Resolve-Path docs/plan).Path + '\computer-use-native'
.venv\Scripts\pytest.exe plugins/computer_use/tests/test_session.py
```

测试记录原始截图、最终截图及不含 Base64 的 JSON。中文、UIA 点击、坐标点击和快捷键均由应用自身保存的状态验证。还验证 stale snapshot、跨屏/主屏外窗口拒绝、主屏最大化、实际 DPI/显示器数量、驱动子进程退出及目标应用仍在运行。测试窗口需要交互式桌面；不改变用户显示器设置，不操作其他应用。测试脚本使用 UTF-8 BOM，以便 Windows PowerShell 5 正确读取中文。

仓库外独立 wheel 验证：

```sh
uv run python scripts/verify_plugin_tests.py --plugins computer_use --output /absolute/path/outside-repository/computer-use-tests
```

插件副本配合私有 wheelhouse：

```sh
uv venv .venv --python 3.12
uv pip install --python .venv --find-links /absolute/path/wheelhouse ".[test]"
uv run --no-project --python .venv python -m pytest -c pyproject.toml tests
```

wheel 环境必须安装真实宿主、默认记忆和 shiori-plugin-testkit；不得引入原仓库的测试目录。
