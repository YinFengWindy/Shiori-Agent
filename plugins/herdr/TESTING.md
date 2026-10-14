# 独立测试

仓库内：`uv run pytest plugins/herdr/tests`。

插件副本与本地 wheelhouse：

```sh
uv venv .venv --python 3.12
uv pip install --python .venv --find-links /absolute/path/to/wheelhouse --refresh-package shiori-sdk ".[test]"
uv run --no-project --python .venv python -m pytest -c pyproject.toml tests
```

测试仅依赖 SDK testing fake。真实 Herdr 验收必须使用专用命名 session 和临时
Git 仓库，不操作其他 pane；包括 Codex/Claude Full Access 启动、需求提交与结果读取。
