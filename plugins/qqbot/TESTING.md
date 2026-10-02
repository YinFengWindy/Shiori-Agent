# 独立运行 Python 测试

将本插件目录复制到 Shiori 仓库外；wheelhouse 只需 `shiori_sdk-3.0.0` wheel。插件声明自己的 httpx/WebSocket 依赖，测试使用 `shiori-sdk[testing]`，不安装宿主或旧 testkit。

```sh
uv venv .venv --python 3.12
uv pip install --python .venv --find-links /path/to/wheelhouse ".[test]"
uv run --no-project --python .venv python -m pytest -c pyproject.toml tests
```

安装不使用 editable，不设置指向原仓库的 `PYTHONPATH`。可用 `shiori_sdk.testing.packages.stage_plugin_package` 暂存插件；SDK 提供独立账号、配置、事件、intake、消息总线和 setup fake。QQBot 网关、凭据交接、头像、目标/附件发送与流式状态的行为验证留在本插件。

真实插件重载、角色删除在宿主 `tests/backend/desktop_bridge/runtime/test_plugin_management_qqbot.py`；真实 AgentLoop/消息总线流式及取消交付在 `tests/backend/agent/looping/test_core_qqbot_streaming.py`。这些集成测试由宿主运行，不是插件独立测试的依赖。
