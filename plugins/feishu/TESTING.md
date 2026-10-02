# 独立运行 Python 测试

将插件复制到 Shiori 仓库外；wheelhouse 只需 `shiori_sdk-3.1.0` wheel。插件显式声明 lark-oapi、httpx、pydantic；测试依赖 SDK testing 与 Pillow，不安装宿主或旧 testkit。

```sh
uv venv .venv --python 3.12
uv pip install --python .venv --find-links /path/to/wheelhouse ".[test]"
uv run --no-project --python .venv python -m pytest -c pyproject.toml tests
```

禁止 editable 安装或指向原仓库的 PYTHONPATH。公共 fake 来自 `shiori_sdk.testing`；平台命令、凭据引用、消息/附件、流式与重连在本插件验证。`ctx.channels.group` 和 `session_manager.identity_index` 注入宿主协调服务；单测用 SDK fake，真实实现不复制到插件。

真实重载、角色/账号删除留在宿主 `tests/backend/desktop_bridge/runtime/test_plugin_management_feishu.py`；真实头像缓存位于宿主 `tests/backend/agent/plugin_host/test_avatars_feishu.py`。平台集成通过公开渠道启动与外部网络替身装配，飞书的独立测试无需宿主 fixture。每轮修改可运行 `uv run python -m scripts.verify_plugin_tests --plugins feishu` 获得仓库外 wheel 安装、来源与异步执行证据。
