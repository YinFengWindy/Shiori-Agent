# Browser Use tests

在仓库根使用当前 checkout 的环境：

```powershell
.venv\Scripts\pytest.exe -c pytest.ini plugins/browser_use/tests tests/backend/agent/mcp tests/backend/agent/test_tool_runtime.py tests/backend/agent/core/passive_turn/test_reasoning_loop.py tests/backend/proactive_v2/test_mcp_sources_async.py
node --test apps/desktop/scripts/browser-runtime.test.mjs apps/desktop/scripts/verify-packaged.test.mjs
```

默认测试只使用受控注入对象和真实本地 stdio 测试进程，不下载或启动 Windows 组件。真实浏览器验收显式开启：

```powershell
pnpm prepare:browser-use
$env:SHIORI_BROWSER_USE_RUNTIME = (Resolve-Path native/browser-use).Path
$env:SHIORI_BROWSER_USE_EVIDENCE = (Resolve-Path docs/plan).Path + '\browser-use-evidence'
.venv\Scripts\pytest.exe -c pytest.ini plugins/browser_use/tests/test_session.py
```

该用例在 localhost 提供受控中文表单，检查 DOM 实际值、滚动位置、tabs、MCP 原图、重启后的 localStorage、所有 owned PID 退出，以及取消后页面没有收到排队导航。输出 PNG 和不含 Base64 的 JSON 证据。无需真实付费模型。

仓库外验证（需包含宿主、default-memory、testkit 的私有 wheelhouse）：

```sh
uv venv .venv --python 3.12
uv pip install --python .venv --find-links /absolute/path/wheelhouse ".[test]"
uv run --no-project --python .venv python -m pytest -c pyproject.toml tests
```

在仓库内建立并审计独立 wheel 环境：

```sh
uv run python scripts/verify_plugin_tests.py --plugins browser_use --output /absolute/path/outside-repository/browser-use-tests
```
