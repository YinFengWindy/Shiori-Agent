# 桌宠 ASR + TTS 供应商选型

> 调研日期：2026-07-25
>
> 场景：Windows 桌面端、Electron 桌宠、中文短语音、按住说话、自动进入角色 Loop、按句播放角色回复、每个角色绑定自定义声音。

## 推荐组合

### TTS：MiniMax Speech-2.8 Turbo / HD

MiniMax 是当前最贴合需求的 TTS 候选：官方接口明确支持中文、流式输出、`voice_id`、声音快速复刻、语速、音量、音高、情绪、发音词典和音色混合。

官方按量价格页面显示：

- `speech-2.8-turbo` 同步/异步 TTS：2 元/万字符。
- `speech-2.8-hd` 同步/异步 TTS：3.5 元/万字符。
- 快速复刻：9.9 元/音色，首次使用该音色合成时收取。
- Turbo 语音资源包：200 万字符 360 元；HD 语音资源包：200 万字符 630 元。
- 资源包附带一定数量的快速克隆音色，具体以官方套餐页面为准。

MiniMax 文档还说明，快速复刻音色如果 7 天内未正式调用会被删除；创建声音前需要完成个人或企业认证。这两个约束必须进入产品流程，不能把“上传后永久存在”当作默认行为。

建议首版使用 Turbo，只有用户明确需要更高保真度时才选择 HD。对桌宠短句而言，Turbo 已经覆盖流式、情绪、声音效果和自定义声音的核心要求。

### ASR：OpenAI `gpt-4o-mini-transcribe` 作为第一候选

ASR 仍然独立于 TTS。OpenAI 的 Speech-to-Text 接口适合短录音转写，当前项目已经使用 OpenAI 兼容的 Python SDK，接入基础较好。此前调研记录中的公开价位约为 0.003 美元/分钟，但实现前必须重新确认模型可用性、区域网络和当前价格。

如果 OpenAI 在目标部署环境中网络不稳定，优先重新评估中国大陆云厂商的 ASR，而不是让 TTS 供应商自动接管 ASR。首版不做隐式跨供应商 fallback。

## 备选对比

| 供应商 | 适合程度 | 已确认能力 | 主要问题 |
| --- | --- | --- | --- |
| MiniMax | 首选 TTS | 中文、流式 TTS、`voice_id`、快速复刻、音高/音量/语速/情绪/发音控制 | 需要认证；复刻音色有使用期限约束；需确认海外部署网络情况 |
| ElevenLabs | 国际 TTS 备选 | API 支持 TTS、流式输出、Instant/Professional Voice Cloning、Python/JavaScript SDK | 价格明显更高；中文与区域网络需要实测；声音资产和套餐按其平台规则管理 |
| Azure AI Speech | 企业合规备选 | 中文标准声音、流式音频、Custom Neural Voice；可调 pitch、rate、intonation 和 pronunciation | 自定义声音需要准备录音和脚本，并可能需要审批/受限访问；资源与区域配置较重 |
| Google Cloud TTS | 标准 TTS 备选 | 多语言标准声音和流式播放 | 不适合作为本项目首选的自定义声音供应商；具体 custom voice 可用性和申请条件需要单独确认 |
| OpenAI TTS | 普通 TTS 备选 | 适合作为固定声音的简单 TTS | 当前选型重点是用户上传样本的自定义声音，不能假设 OpenAI TTS 提供该能力 |

## 角色声音生命周期

```text
用户上传授权录音
  -> TTS provider 创建/复刻音色
  -> 返回 voice_id
  -> 用户试听
  -> 用户绑定到角色
  -> 角色回复按句调用 voice_id
```

Shiori 只保存供应商标识、`voice_id`、声音显示名和配置，不保存原始录音。删除或替换声音时，应调用供应商的声音删除接口；供应商不支持删除时，至少清除本地引用并明确告知用户云端资产仍由供应商保管。

角色没有可用 `voice_id` 时，不调用 TTS，也不偷偷回退到默认声音；文字回复照常显示。TTS 失败只影响语音播放，不影响 Loop 和文字消息。

## 实现前验证

1. 用 100-200 条中文短句测试 ASR 错误率、端到端延迟、键盘声和远场麦克风。
2. 用同一段角色文本测试 MiniMax Turbo、MiniMax HD 和一个国际备选的首句可播放时间、断句自然度、音色相似度和中断行为。
3. 验证 MiniMax 快速复刻的认证、7 天使用期限、删除接口和真实计费。
4. 验证流式 TTS 返回的数据格式能否直接在 Electron 播放，避免每句都落盘成临时文件。
5. 记录 provider、voice_id、耗时、字符数和错误码；默认不记录原始音频和完整 TTS 音频。

## 官方来源

- MiniMax TTS HTTP 接口：<https://platform.minimaxi.com/docs/api-reference/speech-t2a-http>
- MiniMax 按量计费：<https://platform.minimaxi.com/docs/guides/pricing-paygo>
- MiniMax 语音资源包：<https://platform.minimaxi.com/docs/guides/pricing-speech>
- ElevenLabs TTS API：<https://elevenlabs.io/docs/api-reference/text-to-speech/convert>
- ElevenLabs 流式 TTS：<https://elevenlabs.io/docs/api-reference/text-to-speech/stream>
- ElevenLabs 声音克隆与声音 API：<https://elevenlabs.io/docs/api-reference/voices>
- ElevenLabs 官方定价：<https://elevenlabs.io/pricing>
- Azure Custom Neural Voice：<https://learn.microsoft.com/en-us/azure/ai-services/speech-service/custom-neural-voice>
- Azure 文本转语音 REST API：<https://learn.microsoft.com/en-us/azure/ai-services/speech-service/rest-text-to-speech>
- OpenAI Speech-to-Text：<https://platform.openai.com/docs/guides/speech-to-text>
- OpenAI API 定价：<https://openai.com/api/pricing/>

> 价格和模型会更新。本文的 MiniMax 价格来自官方公开页面；OpenAI、ElevenLabs、Azure 的最终费用仍需结合账号、地区、模型和套餐在落地前复核。
