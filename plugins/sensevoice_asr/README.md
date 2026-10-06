# SenseVoiceSmall ASR

独立 Shiori ASR provider，通过 SDK `shiori.asr.v1` 发布 `asr/transcribe`。
不依赖桌宠；其他插件可以动态发现并调用。

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

本包不携带、下载或启动推理环境，不把 torch/FunASR 安装进宿主 `.venv`。
环境准备与真实本机识别、延迟、资源占用验收由 #676 完成。
当前受控协议测试只证明请求/错误处理，不代表实际声学效果。
应用级验收另使用实际安装 ZIP、Electron 生产入口、Python bridge 和本机 HTTP 替身，
以生成 PCM 验证文件与桌宠调用链；真实麦克风识别质量和模型性能仍由 #676 验收。

## 安装与测试

要求 SDK / Runtime API 4.1，manifest 标记 `distribution: external`。
仓库源码不作为内置插件加载；使用通用 builder 生成 ZIP 后从插件页面安装，
经普通信任、启用、更新、停用和卸载流程使用。Python wheel 用于独立测试，
不替代包含前端的安装 ZIP。在仓库根目录构建：

```sh
node scripts/build-plugin.mjs --plugin plugins/sensevoice_asr --output artifacts/plugins
```

从“设置 → 插件 → 安装插件 ZIP”选择产物，确认信任并安装，重启后启用。
独立测试命令见[源码仓库 TESTING.md](https://github.com/YinFengWindy/Shiori-Agent/blob/main/plugins/sensevoice_asr/TESTING.md)。
