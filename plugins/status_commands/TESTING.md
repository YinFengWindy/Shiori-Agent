# 独立运行 Python 测试

将本插件目录复制到 Shiori 仓库外，准备包含 `shiori-sdk` 3.1.1 wheel 的私有 wheelhouse；其他第三方依赖由包元数据解析。状态命令测试还需要 `shiori-plugin-observe` 0.1.0 wheel；它仅在 test extra 中声明，运行时仍是显式可选依赖。


在插件副本目录执行：

```sh
uv venv .venv --python 3.12
uv pip install --python .venv --find-links /path/to/wheelhouse --refresh-package shiori-sdk --refresh-package shiori-plugin-observe ".[test]"
uv run --no-project --python .venv python -m pytest -c pyproject.toml tests
```

这是普通 wheel 安装，不使用 editable，也不需要 `shiori-agent`、`shiori-host-testing` 或默认记忆插件。不要设置 `PYTHONPATH` 指向原仓库，不要复制宿主 tests/conftest。公共测试能力来自 `shiori_sdk.testing`；实际宿主执行、会话事务、配置恢复和全局钩子集成在宿主测试树验证。

仓库维护者可以运行 `uv run python -m scripts.verify_plugin_tests --plugins status_commands`，脚本在仓库外构建和安装 wheel、执行全部单测并审计依赖来源与异步执行。暂存插件包使用 `shiori_sdk.testing.packages.stage_plugin_package`，会排除虚拟环境和构建状态。
