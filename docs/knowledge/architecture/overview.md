---
title: 总体架构
kind: 架构说明
status: 当前有效
last_verified_commit: 27af068a
source_paths:
  - main.py
  - bootstrap/app.py
  - bootstrap/wiring.py
  - bus/
  - agent/core/
related:
  - ../map.md
  - ../modules/agent-lifecycle-and-tools.md
---

# 总体架构

## 启动与装配

`main.py` 是进程入口。`bootstrap/app.py` 管理应用生命周期，`bootstrap/wiring.py` 负责把配置、持久化、角色世界、Session、Agent、工具、插件、渠道和主动循环拼装在一起。具体领域服务应由 owning module 提供，bootstrap 只承担依赖拼接。

## 被动消息主链路

1. 渠道或桌面桥接接收输入并解析角色与会话标识。
2. 输入进入 `bus/`，由 Session/Conversation 保存和投影消息状态。
3. Agent pipeline 准备上下文，注入角色、关系、记忆、技能和可见工具。
4. 推理循环可能调用工具；生命周期 phase 和插件 hook 在相应边界执行。
5. 最终输出写回会话，经统一输出端口投递到来源渠道或桌面端。

## 主动主链路

`proactive_v2/` 根据时间、presence、关系和其他传感结果创建 tick，经过裁定后启动主动 Agent 回合。Drift 是具有独立状态的特殊回合路径。主动输出最终仍复用会话、工具和投递基础设施，避免形成第二套消息系统。

## 权威状态边界

- 角色定义、绑定和素材：`core/roles/`。
- 活跃运行会话：`session/`。
- 可持久化对话线程与投影：`conversation/`。
- 记忆：通过 `core/memory/` 契约，由具体 engine/store 实现。
- 渠道仅负责适配，不应成为角色或会话业务的权威来源。
- 桌面 renderer 是视图和交互层，业务写入应经过 `desktop_bridge/` 对应服务。

## 失败策略

业务层异常默认向边界冒泡。只有渠道投递、typing、后台刷新等明确的边界型辅助动作可以隔离失败；权威数据写入、迁移和核心 Agent 回合不能静默吞错。
