---
title: Graphify 图谱健康与限制
kind: 质量报告
status: 有已知问题
last_verified_commit: 27af068a
source_paths:
  - .graphifyignore
  - graphify-out/health.json
  - graphify-out/GRAPH_REPORT.md
related:
  - ../index.md
  - ../../adr/0001-graphify-backed-project-knowledge-base.md
---

# Graphify 图谱健康与限制

## 当前覆盖

- 语料：535 个文件，约 234,012 词。
- 代码：513 个文件；文档：22 个文件。
- AST：6,058 个节点、19,269 条原始边。
- 文档语义：90 个节点、87 条边、2 个超边。
- 最终可查询图：6,148 个节点、16,957 条边、240 个社区。
- 查询 benchmark：平均约 1,302 tokens，估算比读取全量语料少 314.8 倍。

## 已知健康警告

| 指标 | 数量 | 含义 |
| --- | ---: | --- |
| dangling endpoint edges | 1,476 | 边的一端未能映射到最终节点，相关关系可能缺失 |
| self loops | 6 | 节点指向自身，通常不提供有效导航信息 |
| directed same-endpoint collapsed edges | 940 | 构图时同端点有向边被折叠，细粒度关系类型可能丢失 |
| undirected collapsed edges | 954 | 无向图合并重复端点关系，边数量少于抽取结果 |

图谱仍适合导航和缩小搜索范围，但不能用边数量证明完整性。对删除、迁移、权限、自动触发等高风险结论，必须回到源码和测试核验。

## 成本口径

本次由 Agent 完成的语义提取没有暴露 token usage，Graphify 报告中的输入/输出 token 均为 `0`。这表示“未记录”，不表示语义提取没有消耗，也不应人为补估为真实成本。

## 更新机制

`post-commit` hook 根据变更文件在后台增量重建代码图谱；`post-checkout` 在分支切换后刷新。日志位于用户缓存目录的 `graphify-rebuild.log`。`docs/knowledge/` 的业务解释不会由 hook 自动改写，行为变更仍需人工维护。

## 排除范围

测试、评测、Docker、依赖、构建产物、运行时数据、图片素材、spec、plan 和本地 handbook 不进入主图谱。因此图谱回答的是产品代码架构，不覆盖测试证明、真实用户数据或历史方案全文。
