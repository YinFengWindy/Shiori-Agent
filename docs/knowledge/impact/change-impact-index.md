---
title: 改动影响索引
kind: 影响分析
status: 当前有效
last_verified_commit: 27af068a
source_paths:
  - core/
  - agent/
  - proactive_v2/
  - infra/
  - desktop_bridge/
  - desktop/renderer/src/
related:
  - ../map.md
  - ../quality/graph-health.md
---

# 改动影响索引

在修改前先用本表确定第一圈影响，再用 Graphify 查调用路径和相关社区，最后打开源码核验。

| 准备修改 | 必查影响面 | 推荐图谱查询词 |
| --- | --- | --- |
| 角色 schema / CRUD | store、迁移、world、绑定、Session、关系、任务、桌面共享类型 | `RoleRecord RoleAggregateService RoleWorldRegistry` |
| 关系、心情、寂寞 | relationship runtime、Proactive、提示词、场景、桌面展示 | `RoleRelationshipRuntimeService loneliness snapshot` |
| 角色素材 | 资源存储、桌面素材页、提示词、NovelAI、自动 CG | `RoleAssetsPage LocalAssetRegistry NovelAI` |
| 会话键 / 线程 | 渠道标识、Session、Conversation、群聊记忆、桌面缓存 | `session_key SessionManager ConversationService` |
| 消息模型 / 附件 | bus、投影、渠道格式化、桌面 presenter、记忆采样、自动 CG | `InboundMessage OutboundMessage projector media` |
| 记忆 schema / 检索 | engine、store、索引、过滤、注入、工具、后台写入 | `MemoryEngine MemoryQuery MemoryRetrievalPipeline` |
| Proactive 门控 | sensor、presence、关系、state、Agent tick、投递 | `ProactiveLoop AgentTickFactory ProactiveStateStore` |
| Drift | drift state、pipeline、tools、主动互斥、恢复 | `DriftStateStore DriftTurnPipeline` |
| 自动 CG | phase hook、scene decision、cooldown、scene key、NovelAI、消息同步 | `AutoCgController AutoCgPolicy SceneDecision` |
| NovelAI 请求 | settings、store、手动工具、自动 CG、桌面图片面板 | `NovelAIService GenerateImageRequest` |
| Channel 合约 | 所有渠道、hub、bootstrap、bus、会话解析、附件 | `Channel ChannelContext TelegramChannel QQChannel` |
| Tool 契约 / 执行 | registry、search、hook、插件、MCP、事件、提示词 | `ToolRegistry ToolExecutor ToolHook McpServerRegistry` |
| 生命周期 phase | 所有 phase module、记忆、插件、自动 CG、观测 | `BeforeTurn AfterTurn PhaseModule` |
| MCP | registry、client pool、工具同步、配置、断线清理 | `McpServerRegistry McpClient ToolRegistry` |
| Bridge API | dispatcher、service、presenter、Electron client、renderer hook | `DesktopBridgeService request_dispatcher DesktopBridgeClient` |
| 调度任务 | scheduler、工具、持久化、主动投递、角色删除、桌面表单 | `ScheduleRoleTaskService compute_fire_at` |

## 判断顺序

1. 找 owning module，而不是从 UI 或渠道开始补丁。
2. 查写路径、读路径、事件订阅者和持久化边界。
3. 检查角色、会话、渠道三个标识是否仍保持隔离。
4. 检查后台任务、重试、缓存和派生状态是否会重复执行。
5. 只对实际影响范围运行对应测试；跨模块契约变化再扩大回归范围。
