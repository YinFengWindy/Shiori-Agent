# 独立运行 Python 测试

复制插件到仓库外，准备包含 `shiori-sdk` 3.0.0 wheel 的私有 wheelhouse；无需安装宿主、testkit 或默认记忆。进入插件副本：

```sh
uv venv .venv --python 3.12
uv pip install --python .venv --find-links /path/to/wheelhouse ".[test]"
uv run --no-project --python .venv python -m pytest -c pyproject.toml tests
```

安装不使用 editable，不设置 `PYTHONPATH` 指向原仓库。测试只使用 SDK fake 与声明的 Pillow 依赖，覆盖包校验/导入、角色单点启用、RPC、动作限流和资源清理。整包暂存使用 `shiori_sdk.testing.packages.stage_plugin_package`。

真实 canonical 角色锁、原子保存、升级迁移凭证以及 kernel 停用/重载集成保留在宿主 `tests/backend/agent/plugin_host/test_desktop_pet_*integration.py`，从公开 SDK 能力装配；它们不属于插件的独立安装依赖。
