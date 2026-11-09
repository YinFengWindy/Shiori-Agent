# 独立 Fish Audio 云端语音插件

状态：维护者已确认 [#1010](https://github.com/YinFengWindy/Shiori-Agent/issues/1010) 的首版范围，包含 TTS 和 ASR。

## 所有权和配置入口

`fish_audio` 独立提供 `shiori.tts.v1` 与 `shiori.asr.v1` 服务，不依赖 `desktop_pet`。桌宠及其他调用方通过现有服务发现机制选择并调用它。桌宠的对话、录音手势、直播、播报队列和停止播放继续归桌宠及宿主；Fish 服务只返回合成音频或转写文本。

API Key 和 TTS 模型选择放在 Fish 插件设置中。**声音 ID 和语速属于每个角色，必须在角色详情的 Fish 声音卡片中配置**，存于 Fish 插件自己的角色映射，不写入桌宠配置或全局默认声音。角色删除时清理对应映射。未配置声音时明确报错，不擅自选择其他声音。

维护者随后要求为角色增加语言选择。角色声音卡提供「文本语言」，与声音 ID、语速一起按角色保存。默认「自动」，旧配置缺少语言字段时也使用自动；自动模式不向 Fish 发送 `language`，保留按文本片段识别及混合语言行为。明确选择时传递对应的 BCP-47 标签。

按 Fish 的 [TTS 语言说明](https://docs.fish.audio/features/text-to-speech#language)，该参数只控制数字、日期、单位等文本规范化读法，以及启用时间戳时的对齐；它不传入语音模型，不改变音色或口音，也不翻译回复。角色生成哪种语言的文本仍由其提示词决定。语言选择不加入全局插件设置或 ASR 服务。

插件设置提供 WAV 转写测试；角色声音卡提供试听。两者在桌宠停用时也可使用。试听由 Fish 自身 background 调用宿主原生音频接口，停止或离开角色后丢弃旧合成结果，只停止对应的试听。

## 协议与生命周期

现有 SDK 契约已经足够：TTS 接收文字、角色及 mood，返回完整 MP3；ASR 接收完整 PCM WAV，返回纯文本。首版不自动把 mood 转换为 Fish 情绪标记。

直接使用异步 HTTP 客户端访问 Fish 官方 REST API。与官方 Python SDK 相比，这使 ASR 的 `model` header、`diarize=false` 和 `tag_audio_events=false` 可以显式发送，不需要绕过 SDK 封装；也无需改变 Shiori 的公共插座。

TTS 默认显式选择 `s2.1-pro-free`，允许用户选择 `s2.1-pro` 或 `s2-pro`，不自动切换计费模型。ASR 显式选择 `transcribe-1-pro`，不请求时间戳。免费 TTS 不代表 ASR 免费。

请求有整体期限与数据大小边界，不自动重试可能已计费的操作。API Key 不在读取配置时回显，省略它时保留原值，清除需要明确操作；错误不得泄漏凭据。客户端通过 `ctx.effect` 关闭，服务注销及退役调用结果由现有宿主生命周期边界处理。现有服务契约没有上游请求取消接口，停止播放不能表述为撤销远端请求或计费。

维护者于 2026-11-09 将分发方式调整为随应用提供的本地插件。源码包采用 `distribution: builtin`，由宿主直接发现，前端及后端随应用构建，无需安装 ZIP；默认停用，用户在插件管理中启用。语音服务仍调用 Fish 云端 API，插件自身与桌宠保持独立。

## 验证和范围

定向验证覆盖上游 HTTP 协议、无桌宠服务装配、配置持久化与角色隔离、错误和凭据边界、试听取消与卸载，以及宿主发现、内置前端构建和独立 wheel 隔离。真实账号请求、音质和 Electron 实际音频输出单独记录，不能用 HTTP 替身或单测结果代替。

首版不含本地部署、声音上传或训练、WebSocket 流式语音、新 SDK 扩展面或桌宠语音重构。

来源：[Fish TTS API](https://docs.fish.audio/api-reference/endpoint/openapi-v1/text-to-speech)、[Fish ASR](https://docs.fish.audio/features/speech-to-text)，2026-11-09 核对；本地契约为 `packages/sdk/python/shiori_sdk/voice.py`。
