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

### ASR：腾讯云一句话识别作为第一候选

ASR 仍然独立于 TTS。腾讯云一句话识别官方接口直接支持本地音频数据或公网 URL，适合桌宠的短录音场景；本轮核验确认它支持 60 秒内、3 MB 内的音频。首版不做隐式跨供应商 fallback。

腾讯云接口使用 TC3-HMAC-SHA256 签名，需要 SecretId 和 SecretKey，不能按单一 Bearer API Key 处理。实现时应由腾讯云适配器负责签名，业务层只接收音频和识别参数。

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

## 2026-07-25 官方 API 文档核验

本节只记录腾讯云和 MiniMax 官方页面在 2026-07-25 核验到的接口事实。MiniMax 文档站当前的官方文档索引已经将“流式”入口列为 WebSocket；因此下面同时记录 HTTP TTS 和当前官方 WebSocket 流式协议。早期的 `speech-t2a-streaming` 路径不作为实现依据。

### 腾讯云一句话识别

官方接口页面：

- [一句话识别](https://cloud.tencent.com/document/product/1093/35646)，核验日期 2026-07-25。
- [公共请求参数](https://cloud.tencent.com/document/api/1093/35640)，核验日期 2026-07-25。
- [错误码](https://cloud.tencent.com/document/api/1093/35647)，核验日期 2026-07-25。
- [计费概述（在线版）](https://cloud.tencent.com/document/product/1093/35686)，核验日期 2026-07-25。

核验结果：

| 项目 | 官方定义 |
| --- | --- |
| 认证 | 云 API 3.0 的 `TC3-HMAC-SHA256`。请求头包含 `Authorization`、`X-TC-Action: SentenceRecognition`、`X-TC-Version: 2019-06-14`、`X-TC-Timestamp`；签名凭证使用 SecretId，签名计算使用 SecretKey。可选临时凭证通过 `X-TC-Token` 传入。 |
| URL / 方法 | `https://asr.tencentcloudapi.com/`，`POST /`。官方示例使用 `Content-Type: application/json; charset=utf-8`。 |
| 请求体 | `Action` 和 `Version` 是公共参数；核心字段为 `EngSerViceType`、`SourceType`、`VoiceFormat`。`SourceType=0` 时传 `Url`；`SourceType=1` 时传 Base64 的 `Data` 和未编码前字节数 `DataLen`。可选 `ProjectId`、`SubServiceType`、`WordInfo`、过滤项和热词/替换词 ID。 |
| 音频限制 | 一句话识别音频时长不超过 60 秒，文件大小不超过 3 MB；`Data` 场景的 3 MB 限制按 Base64 后数据描述。支持 `wav`、`pcm`、`ogg-opus`、`speex`、`silk`、`mp3`、`m4a`、`aac`、`amr`。 |
| 响应 | 成功返回 `Response.Result`、`Response.AudioDuration`（毫秒）、可选 `WordSize` / `WordList`，以及 `Response.RequestId`。 |
| 错误 | 失败响应仍是 JSON，形如 `Response.Error.Code`、`Response.Error.Message` 和 `Response.RequestId`。业务错误包含参数无效、音频格式不支持、音频数据无效、音频超时等。 |

官方页面还说明 `Region` 对该接口不是必需输入参数；示例请求可能带 `X-TC-Region`。实现应以接口文档对 `Region` 的定义为准，不把地域字段硬编码为业务必填项。

计费页核验到：一句话识别每月免费额度为 5000 次；预付费资源包有效期为 1 年，页面列出 1 年 3 万次资源包价格 90 元。后付费需手动开启，具体阶梯价格以账号所在区域和当前计费页为准。

### MiniMax Speech-2.8 HTTP TTS

官方页面：

- [同步语音合成 HTTP](https://platform.minimaxi.com/docs/api-reference/speech-t2a-http)，核验日期 2026-07-25。
- [按量计费](https://platform.minimaxi.com/docs/guides/pricing-paygo)，核验日期 2026-07-25。

核验结果：

| 项目 | 官方定义 |
| --- | --- |
| 认证 | `Authorization: Bearer <API_key>`；请求体为 `application/json`。API Key 在 MiniMax 账户的接口密钥页面获取。 |
| URL / 方法 | 默认 `https://api.minimaxi.com/v1/t2a_v2`，备用地址 `https://api-bj.minimaxi.com/v1/t2a_v2`，方法为 `POST`。 |
| 请求体 | 必填 `model`、`text`；桌宠还应传 `stream`、`voice_setting.voice_id` 和 `audio_setting`。`voice_setting` 可设置 `speed` `[0.5,2]`、`vol` `(0,10]`、`pitch` `[-12,12]`、`emotion`；音频可配置采样率、比特率、格式和声道。 |
| 文本限制 | 单次文本小于 10,000 字符；超过 3,000 字符官方建议使用流式输出。短句按句调用符合接口定位。 |
| 音频编码 | HTTP 非流式默认返回 hex；`output_format=url` 只对非流式生效，URL 有效期 24 小时。非流式支持输出 `mp3`、`pcm`、`flac` 等格式，当前参数定义还列出 `wav`、`pcmu_raw`、`pcmu_wav`、`opus`。响应 `extra_info` 包含格式、采样率、比特率、声道、时长、大小和计费字符数。 |
| 非流式响应 | JSON 的 `data.audio` 是合成音频，`data.status=2` 表示结束；`trace_id` 用于定位请求；`base_resp.status_code=0`、`status_msg=success` 表示成功。 |
| 流式 HTTP 行为 | 请求 `stream=true` 时，官方 OpenAPI 同时声明 `application/json` 和 `text/event-stream` 响应。中间 chunk 的 `data.status=1`，结束 chunk 的 `status=2`；音频 chunk 为按顺序拼接的 hex。`stream_options.exclude_aggregated_audio=true` 可让最后 chunk 不再重复返回拼接后的完整音频。 |
| 错误 | 使用 `base_resp.status_code` / `status_msg`，文档列出 `1000` 未知错误、`1001` 超时、`1002` 限流、`1004` 鉴权失败、`1039` TPM 限流、`1042` 非法字符超过 10%、`2013` 参数异常等。 |

按量计费页核验到：`speech-2.8-turbo` 同步/异步 TTS 为 2 元/万字符，`speech-2.8-hd` 为 3.5 元/万字符；计费字符包括标点、空格和回车，中文字符按 1 个汉字计 2 个字符。快速复刻为 9.9 元/音色，费用在首次正式合成使用该音色时收取；试听文本按 TTS 规则计费。

### MiniMax 当前官方流式接口

官方当前页面：

- [同步语音合成 WebSocket](https://platform.minimaxi.com/docs/api-reference/speech-t2a-websocket)，核验日期 2026-07-25。
- [同步语音合成指南](https://platform.minimaxi.com/docs/guides/speech-t2a-websocket)，核验日期 2026-07-25。
- [官方文档索引](https://platform.minimaxi.com/docs/llms.txt)，核验日期 2026-07-25。

官方文档索引当前没有把 `speech-t2a-streaming` 作为独立 HTTP 页面列出，而是列出 WebSocket 流式接口。其实现事实为：连接 `wss://api.minimaxi.com/ws/v1/t2a_v2`，握手使用 `Authorization: Bearer <api_key>`；收到 `connected_success` 后发送 `task_start`，等待 `task_started`，再发送一个或多个 `task_continue`（每次带 `text`），最后发送 `task_finish`。服务端以 `task_continued` 返回音频 chunk，`data.audio` 是 hex，按到达顺序拼接；`is_final=true` 表示本次合成完成。失败事件为 `task_failed`，错误在 `base_resp.status_code` / `status_msg` 中。文档明确列出超时断开、非法事件、空文本、超出字符限制和请求超限等流式错误。

因此，首版要做“按句流式播放”时，应优先按 HTTP TTS 的 `stream=true` 或 WebSocket 二选一，并在适配器内固定一种协议；不能把两者当成同一个 `stream` 请求实现。桌宠短句场景建议先使用 HTTP 流式响应，只有实测首包延迟不足时再切到 WebSocket 长连接。

### MiniMax 声音复刻与 `voice_id` 生命周期

官方页面：

- [音色快速复刻](https://platform.minimaxi.com/docs/api-reference/voice-cloning-clone)，核验日期 2026-07-25。
- [上传复刻音频](https://platform.minimaxi.com/docs/api-reference/voice-cloning-uploadcloneaudio)，核验日期 2026-07-25。
- [上传示例音频](https://platform.minimaxi.com/docs/api-reference/voice-cloning-uploadprompt)，核验日期 2026-07-25。
- [音色快速复刻指南](https://platform.minimaxi.com/docs/guides/speech-voice-clone)，核验日期 2026-07-25。

官方流程和限制：

1. 完成个人或企业认证。
2. `POST https://api.minimaxi.com/v1/files/upload`，`multipart/form-data` 上传 `purpose=voice_clone` 的主音频。支持 `mp3`、`m4a`、`wav`，时长 10 秒至 5 分钟，大小不超过 20 MB。
3. 可选地再次上传 `purpose=prompt_audio` 的示例音频。支持同样格式，时长小于 8 秒，大小不超过 20 MB；在复刻请求中作为 `clone_prompt.prompt_audio`，并同时提供对应的 `prompt_text`。
4. `POST https://api.minimaxi.com/v1/voice_clone`，JSON 必填 `file_id` 和调用方指定的 `voice_id`。自定义 `voice_id` 长度为 8 至 256，首字符为英文字母，只允许数字、字母、`-`、`_`，末尾不能是 `-` 或 `_`，且不能与已有 ID 重复。
5. 可传 `text` 和 `model` 生成试听；试听链接在 `demo_audio`，其文本会正常计入 TTS 费用。复刻接口还支持 `text_validation` 与 `accuracy`，由服务端用 ASR 校验样本文本相似度。

需要修正一个容易误解的设计点：当前 OpenAPI 请求模型要求客户端提供 `voice_id`，响应模型主要返回试听链接、音频元信息和 `base_resp`，并不是“上传后一定由服务端返回一个新 ID”。本地应保存实际提交的 `voice_id`、provider 和复刻文件元数据，并把 7 天未正式调用会被系统删除视为外部生命周期约束。删除或替换绑定前，应清除本地引用；如需删除云端声音，应另行核对官方声音管理删除接口。

### 配置抽象结论

`provider`、`base_url`、`model`、`api_key` 可以作为跨供应商配置的公共外壳，但不能作为完整协议契约：

- MiniMax HTTP TTS 基本可以映射：`base_url` 默认 `https://api.minimaxi.com`，`model` 为 `speech-2.8-turbo` 或 `speech-2.8-hd`，`api_key` 为 Bearer Token；还必须有 `voice_id`、输出格式和流式传输方式。
- 腾讯云 ASR 的 `model` 应映射为 `EngSerViceType`，但认证至少需要 SecretId + SecretKey 和 TC3 签名，单一 `api_key` 不足；`SourceType`、音频格式、Base64 数据或 URL 也是请求契约的一部分。
- 声音复刻不是普通 TTS 请求的一个可选字段，而是独立的文件上传、复刻创建、试听和生命周期管理流程。

建议将供应商接口抽象为三个操作，而不是一个兼容 OpenAI 的通用请求：`transcribe(audio)`、`synthesize(text, voice_id, stream)`、`clone_voice(source_audio, prompt_audio?)`。配置层可以保留公共字段，同时增加 `api_secret` / `secret_key`、`auth_type`、`voice_id` 和 `transport` 等供应商或操作级字段。
