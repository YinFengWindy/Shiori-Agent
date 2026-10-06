# SenseVoiceSmall ASR

独立 Shiori ASR provider，通过 SDK `shiori.asr.v1` 发布 `asr/transcribe`。
不依赖桌宠；其他插件可以动态发现并调用。

## 插件托管环境（Windows x64 / CPU）

在本插件设置选择“插件托管”并保存，再下载环境或导入完整资源 ZIP。准备后自动启动，
再次启用插件会启动已有环境。首次默认为外部服务以保留既有配置；选择托管后不会在失败时
回退到外部地址。停止环境、停用插件与应用退出会回收所属原生进程树。

固定资源包括 Astral CPython 3.12.15（20261003 Windows x64）、FunASR 1.4.16、
PyTorch/torchaudio 2.7.1 CPU、SenseVoiceSmall 与小型 fsmn-vad。本插件的
`backend/packages.lock.json`、`models.lock.json` 与 `runtime_manifest.py` 保存准确
版本、URL、大小和 SHA-256。四个固定源码依赖在私有解释器内离线构建；不会安装到宿主环境。
两个模型均使用绝对本地路径、CPU、关闭更新与远程代码；VAD 保留长录音分段处理。
WAV 显式转单声道/16kHz；模型识别仍可能误字，不把健康检查当作准确率保证。

完全离线 ZIP 的根目录必须包含 `cpython-3.12.15-windows.tar.gz`，以及
`packages/<锁定文件名>`、`models/sensevoice/<锁定模型文件>`、`models/fsmn-vad/<锁定文件>`。
不需要额外 manifest，不要外层目录。清单外的文件不被执行；清单内每项须通过哈希校验。
普通插件 ZIP 仅包含代码、UI 与锁文件；完整推理资源约 1.36 GB，单独下载或导入。

环境位于 `plugin-data/sensevoice_asr/runtime/`：`downloads/` 缓存支持断点续传，
`staging/` 保存未完成安装，`versions/` 保存完整版本，`current.json` 原子切换。
取消、校验失败或新服务启动失败都保留之前的完整版本。准备/启动错误显示在插件 UI，
详见私有 `prepare.log`、`service.log`。服务必须返回本次进程的令牌才可被调用。

## 外部服务

协议固定于官方 FunASR commit `66d7a4c264a5993a2a63ed00c1f402c296ee521a`。
在独立 CPU PyTorch/FunASR 环境中启动：

```sh
funasr-server --host 127.0.0.1 --port 8000 --model sensevoice --device cpu
```

在本插件设置保存 loopback HTTP 地址，点击“检查连接”，再点击“选择 WAV 并转写”。
健康检查验证 `status=ok`、`device=cpu`、`models_loaded` 包含 `sensevoice`。
请求明确发送 `model=sensevoice`，不使用上游默认的 Nano 模型。
连接超时 5 秒，转写读取超时 60 秒，不使用代理、不重试、不跟随重定向。

设置位于 `plugin-data/sensevoice_asr/settings.json`。转写测试只读取原生选择器
`sensevoice_asr-audio` 命名空间暂存的 WAV（上限 32 MiB），处理后移除暂存副本。

本包不携带大型推理资源，不把 torch/FunASR 安装进宿主 `.venv`。
真实打包应用的环境准备、识别、延迟与资源结果在对应 PR 中单独报告。
当前受控协议测试只证明请求/错误处理，不代表实际声学效果。
应用级验收另使用实际安装 ZIP、Electron 生产入口、Python bridge 和本机 HTTP 替身，
以生成 PCM 验证文件与桌宠调用链；真实麦克风识别质量和模型性能仍由 #676 验收。

## 安装与测试

要求 SDK / Runtime API 4.2，manifest 标记 `distribution: external`。
仓库源码不作为内置插件加载；使用通用 builder 生成 ZIP 后从插件页面安装，
经普通信任、启用、更新、停用和卸载流程使用。Python wheel 用于独立测试，
不替代包含前端的安装 ZIP。在仓库根目录构建：

```sh
node scripts/build-plugin.mjs --plugin plugins/sensevoice_asr --output artifacts/plugins
```

从“设置 → 插件 → 安装插件 ZIP”选择产物，确认信任并安装，重启后启用。
独立测试命令见[源码仓库 TESTING.md](https://github.com/YinFengWindy/Shiori-Agent/blob/main/plugins/sensevoice_asr/TESTING.md)。
