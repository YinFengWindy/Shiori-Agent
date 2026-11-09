# Fish Audio

Fish Audio 随 Shiori 提供，在插件管理中启用后配置：

1. **插件设置 → Fish Audio**：保存 API Key，选择语音合成模型。默认 `s2.1-pro-free`；`transcribe-1-pro` 语音识别单独计费。
2. **角色详情 → Fish Audio 声音**：填写这个角色已有的 Fish 声音 ID，选择文本语言、调整语速，等待保存后试听。每个角色独立保存这些设置。
3. 在使用语音的插件（如桌宠）中分别选择 Fish Audio TTS / ASR provider。

Fish Audio 不依赖桌宠。自己的声音试听和 WAV 转写测试可独立使用。Key 仅保存在工作区的插件私有数据里，设置读取不回显；留空保留原 Key，清除必须点击“清除 Key”。该存储不是操作系统凭据保险箱。

文本语言默认“自动识别”，旧角色配置也保留自动识别。显式选择会传入 Fish 的 `language` 参数，用于数字、日期、单位等文本规范化及时间戳对齐；它不会翻译回复、切换声音模型、改变音色或口音。自动识别不发送该参数，保留 Fish 按文本片段检测语言的行为；回复使用什么语言仍由角色设定和对话决定。

公共服务沿用 `shiori.tts.v1` 和 `shiori.asr.v1`。TTS 返回完整 MP3，ASR 接收最多 32 MB 的完整 PCM WAV 并返回纯文本。录音、播放和消费方的队列由调用方及宿主管理。首版不自动注入情绪标记，不包含本地推理、声音上传训练或 WebSocket 流式接口。

停止试听会阻止后续播放，但无法撤销已经发送到 Fish 的云请求或计费。请求最长 90 秒，不自动重试。真实音质、延迟及云端可用性需要使用自己的账号验证。

参考：[Fish TTS](https://docs.fish.audio/api-reference/endpoint/openapi-v1/text-to-speech)、[Fish ASR](https://docs.fish.audio/features/speech-to-text)。
