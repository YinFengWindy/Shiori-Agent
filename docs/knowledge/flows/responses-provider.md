---
title: Responses API Provider 契约
kind: 领域说明
status: 迁移目标基线
related:
  - ../architecture/target-backend-and-migration.md
---

# Responses API Provider 契约

TypeScript provider 使用官方 `openai` SDK 的 `client.responses.create()`。业务层只依赖 Shiori 内部类型，不直接依赖 SDK 的 response union。

## 内部请求与结果

```ts
interface LlmRequest {
  model: string
  input: ResponseInputItem[]
  tools: ToolDefinition[]
  maxOutputTokens?: number
  toolChoice?: ToolChoice
  reasoning?: { effort?: string; summary?: string }
  providerOptions?: Record<string, unknown>
  signal?: AbortSignal
  timeoutMs?: number
}

interface LlmResponse {
  id: string
  outputText: string | null
  outputItems: OutputItem[]
  toolCalls: ToolCall[]
  reasoning?: ReasoningRecord
  usage?: Usage
  incomplete?: { reason: string }
}
```

## Responses 映射

- `messages` 改为 typed `input` items；是否使用 `instructions` 必须由 fixture 锁定，不能无意改变 system/developer 顺序。
- `response.output_text` 只表示可见文本，不包含 reasoning 或工具调用。
- `function_call.arguments` 是 JSON 字符串，必须保留原文并显式解析。
- 工具结果通过带相同 `call_id` 的 `function_call_output` 回传。
- 流式参数按 `item_id/call_id` 聚合，不按 Chat Completions 的 choices/index 聚合。
- reasoning item 应在 `response.output_item.done` 后再持久化完整内容；不能直接把旧 `reasoning_content` 字段照搬过来。
- `previous_response_id` 只能作为可选的远端链路优化，本地 Session transcript 仍是权威。

## 必须保留的现有语义

- Provider-specific strategy、安全错误、上下文超长错误、429/5xx/网络重试和 stream idle timeout。
- `chat.delta`、`chat.tool.started`、`chat.tool.completed`、`chat.done` 和 `chat.error` 的 bridge 事件形状。
- Embedding 的 2000 字符截断、10 条批量、按 index 排序、批间等待、timeout 和 retry。
- API key 只在 Node backend，不能进入 renderer。

## 能力边界

OpenAI-compatible `baseURL` 不代表一定支持 Responses API。Provider 必须在启动或首次请求时明确探测 `responses` 能力；不支持时返回能力错误，不允许静默回退 Chat Completions。

## 主要测试夹具

- 普通文本、多个 function call、分片参数、坏 JSON 参数。
- reasoning output item、summary、incomplete 和 error stream。
- tool call -> execution -> function_call_output -> final response round-trip。
- retry、429、5xx、timeout、abort、stream idle 和中断恢复。
- 历史 `tool_chain` / `reasoning_content` 到 Responses input 的兼容回放。
