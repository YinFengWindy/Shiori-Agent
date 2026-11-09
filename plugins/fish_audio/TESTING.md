# 独立测试

取得插件副本和包含 Shiori SDK 4.1.x 的 wheelhouse，在副本目录运行：

```sh
uv venv .venv --python 3.12
uv pip install --python .venv --find-links /absolute/path/to/wheelhouse --refresh-package shiori-sdk ".[test]"
uv run --no-project --python .venv python -m pytest -c pyproject.toml tests
```

测试仅安装 SDK testing 和本插件依赖，使用受控 HTTP 运输层及合成 WAV，不依赖宿主或桌宠。它守住角色声音隔离、凭据不回显、真实 HTTP 协议、错误及大小/超时边界、文件隔离和卸载清理。

前端并列测试守住角色卡片设置隔离、试听停止/切换的迟到结果及原生播放所有权。协议与组件测试不能替代真实账号 TTS/ASR、Electron 原生试听和音质验收。
