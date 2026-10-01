# citation 插件

记忆引用追踪与遗留协议清理。从工具调用链或回复中已有的引用标记提取记忆 ID，并清理协议标签；不向系统 prompt 注入引用要求，也不要求模型输出引用行。

---

## 接入点

| 接入方式 | 阶段 |
|---|---|
| `after_reasoning_modules()` | `after_reasoning.build_ctx` 之后——提取 cited ID |
| `after_reasoning_modules()` | `after_reasoning.emit` 之后——清理残留协议标签 |

---

## 运作逻辑

### 1. 提取 cited ID（CitationAfterReasoningModule）

推理完成后，兼容 `reply` 尾部已有的 `§cited:[...]§` 标签：

- 若匹配成功，提取 ID 列表，写入 `persist:assistant:cited_memory_ids` slot，并把标签从 reply 中剥除。
- 若 reply 里没有引用行，fallback 到工具调用链：扫描 `recall_memory` 工具的返回结果，从 JSON 里取出 `cited_item_ids` 或 `items[].id`，作为本轮引用 ID。

提取到的 ID 由下游持久化模块写入数据库，用于更新记忆条目的被引用计数和时间戳。

没有引用标记、也没有 `recall_memory` 工具调用结果时，不记录引用 ID；不会仅根据系统注入的记忆推断实际使用情况。

### 2. 清理协议标签（ProtocolTagCleanupModule）

在 persist 之前再做一次扫描，用正则清除 reply 末尾所有残留的 `<tag:value>` 形式协议标签（包括其他插件可能留下的），保证对外输出的文本干净。
