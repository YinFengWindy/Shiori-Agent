# 腾讯云一句话识别引擎参数核验

> 核验日期：2026-07-26
>
> 范围：只核验腾讯云官方 API 文档、官方 SDK 源码和官方服务开通文档，回答 `SentenceRecognition` 是否要求配置 ASR `model`。

## 结论

用户在腾讯云控制台开通语音识别服务或配置 SecretId / SecretKey 时，**不需要填写一个名为 `model` 的配置项**。腾讯云一句话识别也没有独立的 `model` 请求参数。

但是，每次调用 `SentenceRecognition` 时，官方接口要求在请求体中传入必选字段 `EngSerViceType`。该字段的官方名称是“引擎模型类型”，用于选择采样率、语言和场景组合；它不是任意模型名称，也没有文档声明的默认值。

因此，产品层应区分两个概念：

- 供应商配置：地址、SecretId、SecretKey，不应要求普通用户手填“ASR 模型”。
- 请求协议：适配器必须为每次请求提供 `EngSerViceType`；桌面普通话 16k 场景可以由程序固定为 `16k_zh`，需要多语言时再改为受约束的下拉选择。

不应把腾讯云的 `EngSerViceType` 暴露为可随意填写的通用 `model` 文本框，也不应因为界面不要求填写就从请求体中删除该字段。

## 官方证据

### `EngSerViceType` 是必选请求字段

腾讯云官方[一句话识别 API 文档](https://cloud.tencent.com/document/product/1093/35646)的输入参数表将 `EngSerViceType` 标为“是”，类型为 `String`，描述为“引擎模型类型”。同一页面的两个请求示例也都显式传入该字段。

官方文档没有为 `EngSerViceType` 声明默认值。与 `WordInfo`、`FilterDirty` 等明确写出默认值的可选参数不同，缺省该字段不能视为自动选择 `16k_zh`。

截至本次核验，官方页面列出的取值为：

| 场景 | 官方允许值 |
| --- | --- |
| 电话场景 | `8k_zh`、`8k_en` |
| 非电话场景 | `16k_zh`、`16k_zh-PY`、`16k_zh_medical`、`16k_en`、`16k_yue`、`16k_ja`、`16k_ko`、`16k_vi`、`16k_ms`、`16k_id`、`16k_fil`、`16k_th`、`16k_pt`、`16k_tr`、`16k_ar`、`16k_es`、`16k_hi`、`16k_fr`、`16k_de`、`16k_zh_dialect` |

桌面麦克风采集的普通话 16k 音频对应 `16k_zh`。这里的值同时表达采样率和语言/场景，不能用任意厂商模型名称替代。

### 官方 SDK 没有独立的 `model` 字段

腾讯云官方 Node.js SDK 的 [`SentenceRecognitionRequest`](https://github.com/TencentCloud/tencentcloud-sdk-nodejs/blob/master/src/services/asr/v20190614/asr_models.ts) 将 `EngSerViceType: string` 定义为非可选字段，同时定义了必选的 `SourceType` 和 `VoiceFormat`；请求结构中不存在 `Model` 或 `model` 字段。

腾讯云官方 Python SDK 的 [`SentenceRecognitionRequest`](https://github.com/TencentCloud/tencentcloud-sdk-python/blob/master/tencentcloud/asr/v20190614/models.py)同样只定义 `EngSerViceType`，没有独立的通用 `model` 参数，也没有在请求对象中为它写入默认值。

容易混淆的 `CustomizationId` 是可选的“自学习模型 id”。它只在用户明确创建并使用自学习模型时生效，不等于基础识别引擎选择，也不能替代必选的 `EngSerViceType`。

### 控制台开通与请求参数是两层配置

腾讯云官方[服务如何开通](https://cloud.tencent.com/document/product/1093/35693)只要求用户在语音识别控制台开通服务，没有要求在开通流程中选择或填写模型。

这与 API 文档并不冲突：控制台负责开通账号服务，SDK 客户端负责凭据、端点等连接配置，而具体识别引擎由每次 `SentenceRecognition` 请求的 `EngSerViceType` 决定。

## 对 Shiori 配置的影响

当前跨供应商配置如果使用字段名 `model` 承载 `EngSerViceType`，只是 Shiori 内部的兼容包装，不是腾讯云官方协议名称。更准确的处理方式是：

1. 从普通用户设置界面移除自由文本“ASR 模型”输入。
2. 腾讯云适配器内部默认发送 `EngSerViceType = "16k_zh"`，并保证请求中始终存在该字段。
3. 将来支持电话音频、粤语或多方言时，增加名为“识别引擎”或“语言/场景”的枚举选择，不允许填写任意字符串。
4. 不要把 `CustomizationId` 当作基础 ASR 模型配置；只有产品支持腾讯云自学习模型时再单独暴露。

## 官方来源

- 腾讯云一句话识别 API：<https://cloud.tencent.com/document/product/1093/35646>
- 腾讯云服务如何开通：<https://cloud.tencent.com/document/product/1093/35693>
- Tencent Cloud SDK for Node.js 请求类型：<https://github.com/TencentCloud/tencentcloud-sdk-nodejs/blob/master/src/services/asr/v20190614/asr_models.ts>
- Tencent Cloud SDK for Python 请求类型：<https://github.com/TencentCloud/tencentcloud-sdk-python/blob/master/tencentcloud/asr/v20190614/models.py>
