# 领域文档

工程类 skills 在探索代码库时，应按本文件约定读取仓库的领域文档。

## 探索前读取

- 仓库根目录的 **`CONTEXT.md`**；或者
- 如果根目录存在 **`CONTEXT-MAP.md`**，按其中指引读取与当前主题有关的各上下文 `CONTEXT.md`。
- **`docs/adr/`**：读取涉及当前工作区域的 ADR。多上下文仓库还需检查 `src/<context>/docs/adr/` 中限定上下文的决策。

如果这些文件不存在，**静默继续**。不要提示文件缺失，也不要预先建议创建。`/domain-modeling` skill（可通过 `/grill-with-docs` 和 `/improve-codebase-architecture` 触发）会在术语或决策真正明确后按需创建它们。

## 文件结构

单上下文仓库（大多数仓库）：

```
/
├── CONTEXT.md
├── docs/adr/
│   ├── 0001-event-sourced-orders.md
│   └── 0002-postgres-for-write-model.md
└── src/
```

多上下文仓库（根目录存在 `CONTEXT-MAP.md`）：

```
/
├── CONTEXT-MAP.md
├── docs/adr/                          ← system-wide decisions
└── src/
    ├── ordering/
    │   ├── CONTEXT.md
    │   └── docs/adr/                  ← context-specific decisions
    └── billing/
        ├── CONTEXT.md
        └── docs/adr/
```

## 使用术语表中的词汇

输出中命名领域概念时（例如 Issue 标题、重构建议、假设或测试名称），使用 `CONTEXT.md` 中定义的术语，不要改用术语表明确排除的同义词。

如果所需概念尚未出现在术语表中，这通常意味着正在创造项目未使用的词汇（应重新考虑），或领域模型确实存在空缺（记录下来交由 `/domain-modeling` 处理）。

## 标记 ADR 冲突

如果输出与已有 ADR 冲突，应明确指出，不要静默覆盖：

> _与 ADR-0007（事件溯源订单）冲突，但值得重新讨论，因为……_
