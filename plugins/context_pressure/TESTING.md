# 独立运行 Python 测试

将本插件目录复制到仓库外，准备包含 `shiori-sdk` 3.1.0 的私有 wheelhouse。
插件和 SDK 都以普通 wheel 安装；不需要 `shiori-agent`、旧 testkit 或默认记忆插件。

```sh
uv venv .venv --python 3.12
uv pip install --python .venv --find-links /path/to/wheelhouse --refresh-package shiori-sdk ".[test]"
uv run --no-project --python .venv python -m pytest -c pyproject.toml tests
```

不要注入 `PYTHONPATH`，也不要复制宿主测试树或 conftest。测试通过
`shiori_sdk.testing` 的 `FakeFrame`、`FakePluginContext` 和 `sdk_context`
执行真实插件模块。Fake 仅记录贡献，不模拟宿主阶段调度。
真实 Kernel 加载与卸载回归保留在宿主 `test_kernel.py`，由宿主 CI 执行。

仓库维护者可运行 `uv run python -m scripts.verify_plugin_tests`
构建 wheel、逐插件创建干净环境并记录 `provenance.json` 与异步失败探针。
统一契约与构建说明见 `packages/sdk/README.md`。
