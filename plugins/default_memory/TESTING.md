# 独立运行 Python 测试

本插件只依赖 `shiori-sdk` 和声明的第三方包。把插件目录复制到仓库外，准备含
`shiori_sdk-3.0.0` 与 `shiori_plugin_default_memory-0.1.0` wheel 的私有 wheelhouse。
无需安装 Shiori 宿主、testkit 或宿主测试支持。

在插件副本目录执行（替换 wheelhouse 为实际绝对路径）：

```sh
uv venv .venv --python 3.12
uv pip install --python .venv --find-links /path/to/wheelhouse "shiori-plugin-default-memory[test]==0.1.0"
uv run --no-project --python .venv python -m pytest -c pyproject.toml tests
```

安装不使用 editable，不设置 `PYTHONPATH`，不复制宿主 tests/conftest。
测试使用 `shiori_sdk.testing` 的事件、模型结果、角色权限、存储与构造资源替身。
SQLite、检索、去重、撤销和后处理使用插件自己的实现；真实迁移锁、启动、RPC
卸载与会话整理的集成覆盖仍在宿主测试中。

仓库维护者可以执行：

```sh
uv run python -m scripts.verify_plugin_tests --plugins default_memory
```

该命令在仓库外构建并安装普通 wheel，执行全部测试和异步失败探针，检查已安装
代码来源及没有宿主依赖，并留下 results.json、pytest.log 和 provenance.json。
