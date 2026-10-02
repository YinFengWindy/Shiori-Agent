# 独立运行 Python 测试

将本插件目录复制到 Shiori 仓库外；wheelhouse 只需 `shiori_sdk-3.1.0` wheel。插件声明自己的 httpx/WebSocket 依赖，测试使用 `shiori-sdk[testing]`，不安装宿主或旧 testkit。

```sh
uv venv .venv --python 3.12
uv pip install --python .venv --find-links /path/to/wheelhouse ".[test]"
uv run --no-project --python .venv python -m pytest -c pyproject.toml tests
```

安装不使用 editable，不设置指向原仓库的 `PYTHONPATH`。可用 `shiori_sdk.testing.packages.stage_plugin_package` 暂存插件；SDK 提供独立账号、配置、事件、intake、消息总线和 setup fake。QQBot 网关、凭据交接、头像、目标/附件发送与流式状态的行为验证留在本插件。

重启加载、规则持久化与孤儿清理在本插件 `tests/test_plugin.py` 验证；流式预览、取消与不可重发投递在 `tests/test_streaming.py` 用离线官方 HTTP 替身验证。AgentLoop 流式门控、消息总线重试与角色删除等宿主协议由宿主的中性测试覆盖，不是插件独立测试的依赖。
