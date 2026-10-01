# 独立运行 Python 测试

将本插件目录复制到 Shiori 仓库外。准备私有 wheelhouse，其中包含 `shiori-agent`、`shiori-plugin-testkit`、`shiori-host-testing`、`shiori-plugin-default-memory` 和 `shiori-plugin-observe` 的 0.1.0 wheel，以及 `shiori-sdk` 3.0.0 wheel。这些私有包不发布到 PyPI；其余依赖由包元数据解析。

在插件副本目录执行（替换 wheelhouse 绝对路径）：

```sh
uv venv .venv --python 3.12
uv pip install --python .venv --find-links /path/to/wheelhouse /path/to/wheelhouse/shiori_agent-0.1.0-py3-none-any.whl /path/to/wheelhouse/shiori_plugin_testkit-0.1.0-py3-none-any.whl /path/to/wheelhouse/shiori_plugin_default_memory-0.1.0-py3-none-any.whl ".[test]"
uv run --no-project --python .venv python -m pytest -c pyproject.toml tests
```

安装使用非 editable wheel，不设置指向原仓库的 `PYTHONPATH`，也不复制原仓库测试树或根 conftest。测试通过 testkit 的 `plugin_directory("observe")` 定位已安装的 observe；它仅出现在 `test` extra，不是命令插件的运行依赖。

命令插件与 observe 的整包暂存统一使用 testkit 的 `stage_plugin_package`。副本中的 `.venv` 和包含 `pyvenv.cfg` 的自定义 Python 环境不会被复制进临时插件目录，因此可以直接使用上面的副本内环境安装命令。

宿主仓库的 `docs/agents/plugin-testing.md` 说明私有 wheelhouse 与隔离 CI；独立副本的测试不需要该文档所在仓库。
