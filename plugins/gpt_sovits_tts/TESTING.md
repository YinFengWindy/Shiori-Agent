# 独立测试

取得本插件副本和包含 shiori-sdk 4.1 的私有 wheelhouse 后，在副本目录执行：

```sh
uv venv .venv --python 3.12
uv pip install --python .venv --find-links /absolute/path/to/wheelhouse --refresh-package shiori-sdk ".[test]"
uv run --no-project --python .venv python -m pytest -c pyproject.toml tests
```

测试使用 SDK fake 与受控 HTTP 替身，不安装宿主、桌宠、torch、FunASR 或 GPT-SoVITS。
协议测试不会证明真实模型音质、情绪效果、延迟或显存占用；这些验证由 #676 的本机环境交付完成。
