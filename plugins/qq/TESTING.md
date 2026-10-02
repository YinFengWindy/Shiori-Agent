# 独立运行 Python 测试

将本插件复制到 Shiori 仓库外；wheelhouse 只需 `shiori_sdk-3.1.0` wheel。插件声明 httpx、psutil 和 websockets；测试声明 SDK testing、qrcode 与 Pillow，不安装宿主或旧 testkit。

```sh
uv venv .venv --python 3.12
uv pip install --python .venv --find-links /path/to/wheelhouse ".[test]"
uv run --no-project --python .venv python -m pytest -c pyproject.toml tests
```

安装不使用 editable，不设置原仓库 `PYTHONPATH`，不复制根 conftest。可用 `shiori_sdk.testing.packages.stage_plugin_package` 暂存插件。账号/HTTP/头像/进程使用 SDK fake；真实 NapCat 不会被单测安装或启动，私有 profile、端口、二维码、账号、OneBot 与发送/附件规则仍在插件内验证。

宿主保留 `test_plugin_management_qq.py` 的重启/角色删除，`test_account_delivery_qq.py` 的真实投递账本，`test_avatars_qq.py` 的真实头像缓存集成。同步进程能力验证在 `tests/backend/agent/plugin_host/test_processes.py`，与原 `infra/process` WindowsJob 清理及 QQ 管理进程单测一起加入 Windows CI。真机 NapCat 登录仍需 Windows x64 与本机官方 QQ；本次 SDK 迁移不改变它的安装与进程回收策略。
