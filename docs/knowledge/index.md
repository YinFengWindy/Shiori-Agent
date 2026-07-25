---
title: Shiori 项目知识库
kind: 知识库入口
status: 当前有效
last_verified_commit: 27af068a
source_paths:
  - main.py
  - bootstrap/
  - core/
  - agent/
  - proactive_v2/
  - desktop_bridge/
related:
  - map.md
  - architecture/overview.md
  - impact/change-impact-index.md
---

# Shiori 项目知识库

这里记录 Shiori 当前已经实现的能力、模块所有权、关键数据流和修改影响。它面向维护者和 Agent，目标是先定位，再理解，再安全修改。

## 导航

- [能力地图](map.md)：按业务能力找到 owning module。
- [总体架构](architecture/overview.md)：理解启动、消息、Agent 和持久化主链路。
- [改动影响索引](impact/change-impact-index.md)：从准备修改的对象反查联动模块。
- [图谱健康](quality/graph-health.md)：了解 Graphify 的覆盖范围和已知限制。

## 完整验收问题矩阵

| 能力 | 知识页 | 至少应能回答的问题 |
| --- | --- | --- |
| 角色、关系、心情、素材 | [角色领域](modules/roles.md) | 角色由谁持久化；关系和寂寞如何推进；素材如何影响提示词和图片 |
| 会话与对话 | [会话与对话](modules/conversations-and-sessions.md) | Session 与 Conversation 的边界；消息如何投影和同步 |
| 记忆 | [记忆系统](modules/memory.md) | 检索、注入、写入和整理在哪里；多套实现如何分工 |
| 主动行为 | [主动行为与 Drift](modules/proactive-and-drift.md) | tick 如何触发；presence、裁定和投递如何连接 |
| Drift | [主动行为与 Drift](modules/proactive-and-drift.md) | Drift 状态如何持久化；与普通被动回合有何区别 |
| NovelAI 与自动 CG | [NovelAI 与自动 CG](modules/novelai-and-auto-cg.md) | 自动 CG 何时触发；冷却、去重、重试、消息回写如何工作 |
| 渠道 | [渠道系统](modules/channels.md) | Telegram、QQ 和统一 Channel 合约如何连接消息总线 |
| Agent、工具、插件、MCP | [Agent 生命周期与工具](modules/agent-lifecycle-and-tools.md) | 一个回合经历哪些 phase；工具怎样注册、搜索、执行和拦截 |
| 桌面端与桥接 | [桌面端与桥接](modules/desktop-and-bridge.md) | Electron、React 和 Python 服务如何通信；状态由谁装配 |
| 调度与角色任务 | [调度与任务](modules/scheduling.md) | 定时任务如何创建、触发和展示；角色任务如何执行 |
| 本地数据与迁移 | [本地工作区数据](data/local-workspace.md) | 哪些数据是权威数据；删除、迁移和备份要注意什么 |

## 使用原则

知识页是源码核验后的摘要，不是冻结的规范。遇到细节问题，先运行 `graphify query` 缩小范围，再读取 `source_paths` 中的源码。若文档与源码冲突，以源码和实际测试为准，并立即修正文档。
