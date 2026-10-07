# SenseVoiceSmall ASR

独立 Shiori ASR provider，通过 SDK `shiori.asr.v1` 发布 `asr/transcribe`。
不依赖桌宠；其他插件可以动态发现并调用。

## 插件托管环境（Windows x64 / CPU）

在本插件设置选择“插件托管”（自动保存），再下载环境或导入完整资源 ZIP。准备后自动启动，
再次启用插件会启动已有环境。首次默认为外部服务以保留既有配置；选择托管后不会在失败时
回退到外部地址。停止环境、停用插件与应用退出会回收所属原生进程树。

固定资源包括 Astral CPython 3.12.15（20261003 Windows x64）、uv 0.12.23、FunASR 1.4.16、
PyTorch/torchaudio 2.7.1 CPU、SenseVoiceSmall 与小型 fsmn-vad。本插件的
`backend/packages.lock.json`、`models.lock.json` 与 `runtime_manifest.py` 保存准确
版本、URL、大小和 SHA-256。固定 uv 以 offline/no-index/require-hashes 安装全部 74 个
锁定依赖，其中四个源码包通过标准 setuptools backend 离线构建，不修改上游源码。
构建使用各包独立的短 bdist 目录，避免 Windows 的旧式路径限制；不会安装到宿主环境。
两个模型均使用绝对本地路径、CPU、关闭更新与远程代码；VAD 保留长录音分段处理。
WAV 显式转单声道/16kHz；模型识别仍可能误字，不把健康检查当作准确率保证。

完全离线 ZIP 的根目录必须包含 `cpython-3.12.15-windows.tar.gz`、
`uv-0.12.23-windows-x64.zip`，以及
`packages/<锁定文件名>`、`models/sensevoice/<锁定模型文件>`、`models/fsmn-vad/<锁定文件>`。
不需要额外 manifest，不要外层目录。清单外的文件不被执行；清单内每项须通过哈希校验。
插件本身仅包含代码、UI 与锁文件；完整包包含 85 个锁定资源，共 1,373,095,206 字节
（约 1.37 GB），单独下载或导入。

环境位于 `plugin-data/sensevoice_asr/runtime/`：`downloads/` 缓存支持断点续传，
`s/<id>/` 保存未完成安装，`v/<id>/p/` 保存完整 Python 环境，`current.json` 原子切换。
版本与资源身份保存在校验记录中。`u/`、`t/`、`b/` 分别用于私有安装缓存、临时文件和构建。
服务保留普通 Python prefix；受控文件操作使用扩展路径，无需修改 Windows 注册表或移动工作区。
取消、校验失败或新服务启动失败都保留之前的完整版本。准备/启动错误显示在插件 UI，
详见私有 `prepare.log`、`service.log`。服务必须返回本次进程的令牌才可被调用。

## 外部服务

协议固定于官方 FunASR commit `66d7a4c264a5993a2a63ed00c1f402c296ee521a`。
在独立 CPU PyTorch/FunASR 环境中启动：

```sh
funasr-server --host 127.0.0.1 --port 8000 --model sensevoice --device cpu
```

在本插件设置填写 loopback HTTP 地址（自动保存），点击“检查连接”，再点击“选择 WAV 并转写”。
健康检查验证 `status=ok`、`device=cpu`、`models_loaded` 包含 `sensevoice`。
请求明确发送 `model=sensevoice`，不使用上游默认的 Nano 模型。
连接超时 5 秒，转写读取超时 60 秒，不使用代理、不重试、不跟随重定向。

设置位于 `plugin-data/sensevoice_asr/settings.json`。转写测试只读取原生选择器
`sensevoice_asr-audio` 命名空间暂存的 WAV（上限 32 MiB），处理后移除暂存副本。

本包不携带大型推理资源，不把 torch/FunASR 安装进宿主 `.venv`。
真实打包应用的环境准备、识别、延迟与资源结果在对应 PR 中单独报告。
当前受控协议测试只证明请求/错误处理，不代表实际声学效果。
应用级验收另使用启用的内置插件、Electron 生产入口、Python bridge 和本机 HTTP 替身，
以生成 PCM 验证文件与桌宠调用链；真实麦克风识别质量和模型性能仍由 #676 验收。

## 启用与测试

要求 SDK / Runtime API 3.1.6。本插件随应用内置，新配置下默认停用；在“设置 → 插件”
启用后出现设置页，并可在桌宠语音中选择。Python wheel 仅用于独立测试。
独立测试命令见[源码仓库 TESTING.md](https://github.com/YinFengWindy/Shiori-Agent/blob/main/plugins/sensevoice_asr/TESTING.md)。
