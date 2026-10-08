# 独立运行 Python 测试

复制插件到仓库外，准备包含 `shiori-sdk` 3.1.4 wheel 的私有 wheelhouse；无需安装宿主、testkit 或默认记忆。进入插件副本：

```sh
uv venv .venv --python 3.12
uv pip install --python .venv --find-links /path/to/wheelhouse --refresh-package shiori-sdk ".[test]"
uv run --no-project --python .venv python -m pytest -c pyproject.toml tests
```

安装不使用 editable，不设置 `PYTHONPATH` 指向原仓库。插件声明 httpx、Pillow、pydantic 与 qrcode（B 站登录二维码 PNG）；测试只额外依赖 SDK testing，覆盖包校验/导入、角色单点启用、RPC、动作限流、资源清理和 B 站扫码登录。整包暂存使用 `shiori_sdk.testing.packages.stage_plugin_package`。

B 站扫码登录全程不联网：`tests/conftest.py` 的 `bilibili` fixture 用 `httpx.MockTransport` 脚本化 generate / poll / nav 三个接口，测试通过 `scan_code`（86101/86090/86038/0）、`login_valid` 切换平台响应，并经 `BilibiliLoginApi(transport)` 注入；`gate` + `hold_path` 可挂起指定接口的响应，用于验证退出登录、并发轮询和角色删除与在途请求的竞态。真机仍需验收：真实扫码成功后取得 Cookie、`nav` 返回昵称、登录态失效时状态为 `invalid`。

真实 canonical 角色锁、原子保存、升级迁移凭证以及 kernel 停用/重载集成保留在宿主 `tests/backend/agent/plugin_host/test_kernel_desktop_pet.py`，经真实内核加载插件、只通过公开 RPC 与宿主角色存储断言；它们不属于插件的独立安装依赖。
