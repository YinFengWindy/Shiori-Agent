# 独立运行 Python 测试

将本插件目录复制到 Shiori 仓库外。准备私有 wheelhouse，其中必须有 `shiori-agent`、`shiori-plugin-testkit`、`shiori-plugin-default-memory` 的 0.1.0 wheel。这些私有包不发布到 PyPI；其余第三方依赖由包元数据解析。

在插件副本目录执行（将 `/path/to/wheelhouse` 替换为实际绝对路径）：

```sh
uv venv .venv --python 3.12
uv pip install --python .venv --find-links /path/to/wheelhouse /path/to/wheelhouse/shiori_agent-0.1.0-py3-none-any.whl /path/to/wheelhouse/shiori_plugin_testkit-0.1.0-py3-none-any.whl /path/to/wheelhouse/shiori_plugin_default_memory-0.1.0-py3-none-any.whl ".[test]"
uv run --no-project --python .venv python -m pytest -c pyproject.toml tests
```

安装不使用 editable。不要设置 `PYTHONPATH` 指向原仓库，也不要复制原仓库 `tests/` 或根 conftest。全部测试使用标准 pytest-asyncio；公共启动 fixture 由显式安装的 testkit 注册。需要暂存整个插件时，调用 `shiori_plugin_testkit.packages.stage_plugin_package(source, target)`；它会排除本地虚拟环境与构建/运行状态，允许按上述方式把 `.venv` 留在插件副本内。

宿主仓库中的 `docs/agents/plugin-testing.md` 说明 wheelhouse 构建与 CI 隔离验收；本插件的运行不依赖该文档所在仓库。
