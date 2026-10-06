# 独立测试

在插件副本目录创建虚拟环境后，安装本插件及 SDK testing extra：

```sh
uv pip install --python .venv --find-links /absolute/path/to/wheelhouse --refresh-package shiori-sdk ".[test]"
uv run --no-project --python .venv python -m pytest -c pyproject.toml tests
```
