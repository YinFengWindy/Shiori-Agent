# 桌宠云端语音转写服务选型

> 调研日期：2026-07-25
> 
> 场景：Windows 桌面端、Electron 桌宠、按住说话、短中文语音、转写完成后自动进入现有角色 Loop。

## 结论

首版推荐使用 **OpenAI `gpt-4o-mini-transcribe`**，通过独立的语音转写适配器接入，不把音频送入现有聊天模型接口。

理由：

- 当前项目已经使用 OpenAI 兼容的 Python SDK，认证和请求配置已有可复用基础。
- 官方提供专用 Speech-to-Text 接口，适合把短录音转成文本后再调用现有 `chat.send`。
- `gpt-4o-mini-transcribe` 的公开价位约为 **0.003 美元/分钟**，对于桌宠短句通常远低于角色回复本身的成本；实际账单仍应在实现前重新确认。
- 不需要给安装包增加本地模型，也不需要在本地维护 GPU/CPU 推理环境。

首版不建议同时做多个供应商的自动 fallback。语音识别错误和重试策略需要可观测；自动切换供应商会让同一句话在不同失败场景下得到难以预测的结果。可以先定义 `SpeechToText` 接口，后续用国内供应商替换或增加手动选择。

## 对比

| 服务 | 适配判断 | 成本判断 | 主要风险 |
| --- | --- | --- | --- |
| OpenAI Speech-to-Text | 首选。独立音频转写接口，项目已有 OpenAI 兼容客户端基础 | `gpt-4o-mini-transcribe` 公开价位约 $0.003/分钟 | 需要确认部署地区的网络稳定性、数据处理政策和账号可用模型 |
| Deepgram | 很适合作为技术备选，提供预录音和实时转写接口 | 公开价格通常约 $0.004/分钟级别，具体随模型和模式变化 | 中文模型、区域可用性和最终报价需要用真实账号确认；项目没有现成 Deepgram 客户端 |
| Google Cloud Speech-to-Text | 能力成熟，适合企业级和多语言场景 | 常规识别公开价位约 $0.016/分钟级别，明显高于 OpenAI mini 转写 | GCP 项目、服务账号和计费配置更重；对桌宠短句未显示出足够的性价比优势 |
| Azure AI Speech | Windows 生态和企业合规场景友好 | 常规识别公开价位约 $1/小时级别，约 $0.016/分钟 | Azure 资源和区域配置较重，接入成本高于当前项目所需 |
| 腾讯云 / 阿里云 / 火山引擎 | 中国大陆网络和中文场景值得做区域备选 | 通常按调用或音频时长计费，价格可能更低，但活动、地域、套餐差异较大 | 本次未能在不登录账号的情况下稳定确认与上述国际服务同口径的当前价格；需要真实账号、地域和接口规格做小样本压测 |

## 适合本项目的请求链路

```text
桌宠 renderer
  -> Electron IPC / desktop bridge
  -> SpeechToText provider
  -> { text, language, duration, provider_request_id }
  -> 现有 chat.send
  -> 角色 Loop
```

原始音频只在转写请求生命周期内存在；默认不落盘、不写入会话、不作为角色上下文保存。会话中保存的是用户最终发送的文本，以及必要的 `voice_input` 元数据。

## 必须在实现前确认的事项

1. 用 100-200 条真实中文短句覆盖安静环境、键盘声、远场麦克风、方言/口语和中英混说，比较错误率和端到端延迟。
2. 用真实账号确认 OpenAI 当前可用的转写模型、区域网络、音频格式和限制。
3. 确认服务商的数据保留、训练使用和删除政策；界面应明确提示“语音会上传到云端转写”。
4. 记录转写耗时、失败原因、音频时长和最终文本，但不要默认记录原始音频。
5. 失败时直接提示重录，不自动切换另一个供应商；用户主动选择备用供应商后再重试。

## 官方来源

- OpenAI Speech-to-Text 指南：<https://platform.openai.com/docs/guides/speech-to-text>
- OpenAI API 定价：<https://openai.com/api/pricing/>
- Deepgram STT 定价：<https://deepgram.com/pricing>
- Deepgram 模型与语言支持：<https://developers.deepgram.com/docs/models-languages-overview>
- Google Cloud Speech-to-Text 定价：<https://cloud.google.com/speech-to-text/pricing>
- Google Cloud Speech-to-Text 语言支持：<https://cloud.google.com/speech-to-text/docs/speech-to-text-supported-languages>
- Azure AI Speech 定价：<https://azure.microsoft.com/en-us/pricing/details/cognitive-services/speech-services/>
- Azure AI Speech 语言支持：<https://learn.microsoft.com/en-us/azure/ai-services/speech-service/language-support>
- 腾讯云语音识别产品文档：<https://www.tencentcloud.com/document/product/1093>
- 阿里云智能语音交互文档：<https://www.alibabacloud.com/help/en/isi>
- 火山引擎语音技术文档：<https://www.volcengine.com/docs/6561>

> 价格是公开页面的粗粒度比较，不是最终报价。国际服务的价格和模型会更新，国内服务还会受到地域、套餐和接口规格影响；落地前必须用实际账号重新核价。
