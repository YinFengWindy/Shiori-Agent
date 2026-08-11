# LiteLLM 上下文预算与 Compaction 能力核验

> 核验日期：2026-08-10。来源限定为 LiteLLM 官方文档与 `BerriAI/litellm` 官方仓库。

## 结论

LiteLLM 可以作为 Shiori 新版上下文管理的底层能力，但不能完整替代会话层的 `CompactionController`。

建议复用：

- provider-aware token counting（优先 provider 原生计数，必要时本地 tokenizer fallback）；
- 模型上下文/输入输出上限元数据与 `get_model_info()` / `get_max_tokens()`；
- `context_management` 的自动摘要协议，或把 LiteLLM 作为 summary model provider；
- usage、success/failure callbacks，用于记录压缩前后及摘要调用成本。

Shiori 仍需实现：

- 会话级 cursor、压缩快照版本和并发提交语义；
- 手动 `/compact` 命令及产品化状态展示；
- 原始消息持久化、回溯检索和压缩失败后的恢复；
- 与 Shiori 的角色记忆、工具链和 prompt-cache 周期相协调的保留策略。

## 1. 模型上下文元数据与 Token 预算

LiteLLM 的官方模型注册表 `model_prices_and_context_window.json` 为模型记录提供 `max_input_tokens`、`max_output_tokens` 和遗留字段 `max_tokens`。字段含义在官方 JSON Schema 中明确：`max_input_tokens` 是模型接受的 prompt/context 上限，`max_output_tokens` 是单次生成上限，`max_tokens` 是兼容旧配置的字段。

- Schema：[model_prices_and_context_window.schema.json](https://github.com/BerriAI/litellm/blob/main/model_prices_and_context_window.schema.json#L332-L349)
- Registry：[model_prices_and_context_window.json](https://github.com/BerriAI/litellm/blob/main/model_prices_and_context_window.json)
- 查询实现：[`get_max_tokens()`](https://github.com/BerriAI/litellm/blob/main/litellm/utils.py#L4835-L4894)

`get_modified_max_tokens()` 会调用 `get_model_info()`、`get_max_tokens()` 和 `token_counter()`，在模型的输入+输出共享上限时下调用户请求的输出 token；这解决的是请求参数校正，不是会话压缩策略。未知或自定义模型需要补充/注册模型信息，不能把社区 registry 当成运行时 provider 的绝对真值。

- 参数校正实现：[token_counter.py](https://github.com/BerriAI/litellm/blob/main/litellm/litellm_core_utils/token_counter.py#L39-L114)
- 自定义注册入口：[register_model()](https://github.com/BerriAI/litellm/blob/main/litellm/utils.py#L2715-L2815)

## 2. Token counting

LiteLLM 的 `token_counter()` 支持按模型 tokenizer 计算消息、文本和工具相关内容。`acount_tokens()` 等异步路径会优先调用 provider 原生 count-tokens API，在 provider 不支持或缺少凭据时 fallback 到本地 tokenizer；因此可以用它估算 Shiori 的完整请求预算，但应把 fallback 误差纳入安全余量。

- 官方文档：[Count Tokens](https://docs.litellm.ai/docs/count_tokens)
- 实现：[token_counter.py](https://github.com/BerriAI/litellm/blob/main/litellm/litellm_core_utils/token_counter.py#L334-L380)
- 原生计数与本地 fallback 调度：[main.py](https://github.com/BerriAI/litellm/blob/main/litellm/main.py#L8780-L8820)

## 3. `context_management`：最接近 Claude Code 式 compaction

LiteLLM 官方提供 `context_management` 的 `compact_20260112` 编辑器。它在请求层按 `input_tokens` 触发阈值，调用单独配置的 `context_management_summary_model` 生成摘要，把摘要注入 system prefix，并向客户端返回 compaction block。后续请求若带有已有 compaction block，会丢弃该 block 之前的内容，保留摘要和 compaction 后的尾部。

- 官方文档：[Claude Code Context Management](https://docs.litellm.ai/docs/claude_code_context_management)
- 编辑器实现：[compact.py](https://github.com/BerriAI/litellm/blob/litellm_internal_staging/litellm/llms/anthropic/experimental_pass_through/context_management/editors/compact.py)

已核验的限制：

- 当前 trigger 类型是 `input_tokens`；默认阈值 150,000，显式阈值低于 50,000 会被拒绝。
- trigger 是绝对 token 数，不会按当前模型的 context-window 比例自动推导；模型相对预算仍需由 Shiori 计算。
- 必须配置 summary model；未配置时是 no-op 或返回 `summary_model_not_configured`。
- summary 调用/结果提取失败时，LiteLLM 会原样转发原会话并报告 `summary_call_failed` 或 `summary_extraction_failed`。
- provider matrix 包含 Anthropic/Bedrock/OpenAI Responses 原生或 passthrough，OpenAI Chat、Azure、xAI、Gemini、Vertex 等走 polyfill；具体 provider 行为应以文档矩阵为准。
- `pause_after_compaction` 等部分协议参数目前会被接受但忽略，不能据此实现交互暂停或精细清理策略。
- 这是请求协议/代理层能力，不保存 Shiori 的 session cursor、原始历史或手动命令状态。

因此它可以承接“按模型上下文预算自动摘要”的模型调用和协议拼装，但 Shiori 仍要决定何时提交快照、如何与自身消息库和工具链并发协调。另需评估最低 50k trigger 是否适合 Shiori 使用的小上下文模型。

## 4. 通用 `litellm.compress()`：相关性压缩，不等同于会话摘要

LiteLLM 还提供 `litellm.compress(messages, model, compression_trigger, compression_target)`：默认输入超过 200,000 token 才压缩，目标约为 trigger 的 70%；用 BM25，可选 embedding，对消息按相关性排序，低相关消息替换为 stub，并返回原文 cache 和 `litellm_content_retrieve` 检索工具。低于 trigger 时原样返回。

- 官方文档：[Prompt Compression](https://docs.litellm.ai/docs/completion/prompt_compression)
- 实现：[compress.py](https://github.com/BerriAI/litellm/blob/main/litellm/compression/compress.py#L333-L509)
- 保护规则（system、最后 user/assistant）：[compress.py](https://github.com/BerriAI/litellm/blob/main/litellm/compression/compress.py#L198-L239)

这不是 Codex/Claude Code 式的结构化会话摘要：它会改变消息列表、引入 stub 和 retrieval tool，可能破坏稳定 prompt 前缀，反而影响缓存命中。它适合作为超长历史的可选相关性压缩器，不应直接替换 Shiori 的正常-session consolidation。

## 5. Context-window fallback 与观测

LiteLLM 将 provider 报告的上下文超限归类为 `ContextWindowExceededError`，Router 支持配置 `context_window_fallbacks` 在该错误上切换模型。该机制是失败后的模型路由，不会缩短当前会话，也不会生成摘要。

- Router 配置与处理：[router.py](https://github.com/BerriAI/litellm/blob/main/litellm/router.py#L396-L460) 、[router.py](https://github.com/BerriAI/litellm/blob/main/litellm/router.py#L6280-L6308)
- 异常定义：[exceptions.py](https://github.com/BerriAI/litellm/blob/main/litellm/exceptions.py#L503-L526)

completion 默认返回 usage；LiteLLM 的 input/success/failure callbacks 和自定义 logger 可记录 provider usage、计数和失败原因，适合接入 Shiori 的 compaction telemetry，但 callback 本身不维护会话状态。

- 官方文档：[Token Usage](https://docs.litellm.ai/docs/completion/token_usage)
- 官方文档：[Callbacks](https://docs.litellm.ai/docs/observability/callbacks)

## 对 Issue #64 的落地建议

1. 用 LiteLLM token counting + model metadata 计算每轮实际输入预算，并保留 Shiori 自己的 safety margin。
2. 首选评估 `context_management/compact_20260112`：将 LiteLLM summary model 接入现有 consolidation provider，但由 Shiori 持有 cursor、快照、原始历史和手动 `/compact`。
3. 仅在确有需要时引入 `litellm.compress()`，并单独评估 stub/retrieval 对 prompt cache 和工具链的影响。
4. 为自动压缩、手动压缩、summary 失败、超限 fallback 分别记录 usage 与状态；不要把 LiteLLM fallback 当作 compaction 成功。
