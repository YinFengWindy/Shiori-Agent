# 独立测试

取得本插件副本和包含 shiori-sdk 3.1.4 的私有 wheelhouse 后，在副本目录执行：

```sh
uv venv .venv --python 3.12
uv pip install --python .venv --find-links /absolute/path/to/wheelhouse --refresh-package shiori-sdk ".[test]"
uv run --no-project --python .venv python -m pytest -c pyproject.toml tests
```

测试使用 SDK fake 与受控 HTTP 替身，不安装宿主、桌宠、torch、FunASR 或 GPT-SoVITS。
协议测试不会证明真实模型音质、情绪效果、延迟或显存占用；这些验证由 #676 的本机环境交付完成。

宿主应用级验收位于仓库 `apps/desktop/tests/plugin-ui/`，在插件页启用两个内置 provider，使用
隔离工作区与 userData、Electron 生产入口及真实 Python bridge。私有情绪 UI 使用空角色目录，
通过“添加情绪”创建多个参考映射；桌宠组合场景使用确定性的原生音频输入、ASR/LLM/TTS HTTP
替身和生成 PCM，保留真实聊天、服务调用及播放停止链路。该层需要宿主开发环境，不属于本包
独立测试，也不表示真实模型或声学验收通过。
