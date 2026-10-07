---
title: 总体架构
kind: 架构说明
status: 当前有效
last_verified_commit: bdfdae59
source_paths:
  - apps/backend/main.py
  - apps/backend/bootstrap/app.py
  - apps/backend/bootstrap/tools.py
  - apps/backend/bootstrap/wiring.py
  - apps/backend/bootstrap/runtime/
  - apps/backend/bus/
  - apps/backend/agent/core/
  - apps/backend/agent/looping/core/processing.py
related:
  - ../map.md
  - current-backend.md
  - ../modules/agent-lifecycle-and-tools.md
---

# 总体架构

## 启动与装配

`apps/backend/main.py` 是进程入口（默认命令 `bridge`，另有 `init` 和 `--inspect-modules`）。`apps/backend/bootstrap/app.py` 的 `AppRuntime` 管理应用生命周期；`apps/backend/bootstrap/tools.py` 的 `build_core_runtime()` 把配置、持久化、角色运行时、Session、Agent、工具、记忆、MCP 和插件内核拼装成一代 `CoreRuntime`；`apps/backend/bootstrap/wiring.py` 只维护 memory engine、context builder 和 toolset provider 的名字到工厂映射。`apps/backend/bootstrap/runtime/` 负责运行时换代：设置保存时准备新一代 `CoreRuntime` 并发布，旧代在已接收工作完成后退役。具体领域服务应由 owning module 提供，bootstrap 只承担依赖拼接。

## 被动消息主链路

1. 渠道或桌面桥接接收输入并解析角色与会话标识。
2. 渠道输入进入 `apps/backend/bus/`，由 `RuntimeDispatcher` 消费并交给当代 `AgentLoop.process_inbound()`；桌面聊天由 `DesktopChatService` 直接调用 `AgentLoop.process_direct()`，不经过 bus。两条路径都通过 `RoleRuntimeRegistry.dispatch_passive_turn()` 进入角色级串行执行，由 Session/Conversation 保存和投影消息状态。
3. Agent pipeline 准备上下文，注入角色、关系、记忆、技能和可见工具；输入超出模型预算时按上下文压缩策略处理。
4. 推理循环可能调用工具；生命周期 phase 和插件 hook 在相应边界执行。
5. 最终输出写回会话，经统一输出端口投递到来源渠道或桌面端。

## 主动主链路

`apps/backend/proactive_v2/` 根据时间、presence、关系和其他传感结果创建 tick，经过裁定后启动主动 Agent 回合。Drift 是具有独立状态的特殊回合路径。主动输出最终仍复用会话、工具和投递基础设施，避免形成第二套消息系统。

## 权威状态边界

- 角色定义、绑定和素材：`apps/backend/core/roles/`。
- 活跃运行会话：`apps/backend/session/`。
- 可持久化对话线程与投影：`apps/backend/conversation/`。
- 记忆：契约在 SDK 的 `shiori_sdk.memory`，宿主侧 `apps/backend/core/memory/` 组合 Markdown 记忆与所选 engine（默认 `plugins/default_memory/`）。
- 渠道仅负责适配，不应成为角色或会话业务的权威来源；外部渠道全部以插件形式提供。
- 桌面 renderer 是视图和交互层，业务写入应经过 `apps/backend/desktop_bridge/` 对应服务。

## 失败策略

业务层异常默认向边界冒泡。只有渠道投递、typing、后台刷新等明确的边界型辅助动作可以隔离失败；权威数据写入、迁移和核心 Agent 回合不能静默吞错。
