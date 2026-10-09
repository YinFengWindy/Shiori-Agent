# 独立运行 Python 测试

将本插件复制到 Shiori 仓库外；wheelhouse 需要 `shiori_sdk-3.1.18` 或更新的兼容 wheel。插件声明 httpx、psutil 和 websockets；测试声明 SDK testing、qrcode 与 Pillow，不安装宿主或旧 testkit。

```sh
uv venv .venv --python 3.12
uv pip install --python .venv --find-links /path/to/wheelhouse --refresh-package shiori-sdk ".[test]"
uv run --no-project --python .venv python -m pytest -c pyproject.toml tests
```

安装不使用 editable，不设置原仓库 `PYTHONPATH`，不复制根 conftest。可用 `shiori_sdk.testing.packages.stage_plugin_package` 暂存插件。账号/HTTP/头像/进程使用 SDK fake；真实 NapCat 不会被单测安装或启动，私有 profile、端口、二维码、账号、OneBot 与发送/附件规则仍在插件内验证。

重启加载、孤儿清理与规则持久化在本插件 `tests/test_plugin.py` 验证；投递账本、头像缓存、角色删除等宿主协议由宿主的中性测试覆盖。同步进程能力验证在 `tests/backend/agent/plugin_host/test_processes.py`，与原 `infra/process` WindowsJob 清理及 QQ 管理进程单测一起加入 Windows CI。真机 NapCat 登录仍需 Windows x64 与本机官方 QQ；本次 SDK 迁移不改变它的安装与进程回收策略。
