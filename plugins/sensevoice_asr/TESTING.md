# 独立测试

取得本插件副本和包含 shiori-sdk 3.1.4 的私有 wheelhouse 后，在副本目录执行：

```sh
uv venv .venv --python 3.12
uv pip install --python .venv --find-links /absolute/path/to/wheelhouse --refresh-package shiori-sdk ".[test]"
uv run --no-project --python .venv python -m pytest -c pyproject.toml tests
```

测试使用 SDK fake 与受控 HTTP 替身，不安装宿主、桌宠、torch、FunASR 或 GPT-SoVITS。
仓库 `apps/desktop/tests/plugin-ui/` 中的应用级验收另启用内置 provider，使用隔离 Electron
工作区、真实 Python bridge 与本机 HTTP 替身；生成 PCM/确定性原生音频输入仅替代测试输入。
组合场景保留桌宠到 ASR、聊天、TTS 和播放的实际调用链，不属于插件独立单测。
协议测试不会证明真实模型音质、情绪效果、延迟或显存占用；这些验证由 #676 的本机环境交付完成。
