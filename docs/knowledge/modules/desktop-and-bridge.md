---
title: 桌面端与桥接
kind: 领域说明
status: 当前有效
last_verified_commit: e6877d7a
source_paths:
  - desktop/src/
  - desktop/renderer/src/
  - desktop_bridge/
related:
  - roles.md
  - conversations-and-sessions.md
  - scheduling.md
---

# 桌面端与桥接

## 三层结构

- `desktop/src/`：Electron 主进程、窗口、本地资源传输和 Python bridge client。
- `desktop/renderer/src/`：React 界面，包含应用状态装配、聊天、角色、设置、图片和任务页面。
- `desktop_bridge/`：Python 业务边界，按 app、chat、role、image、schedule/role task 等职责拆分 service 与 presenter。

`DesktopAppFrame.tsx` 只应装配状态、依赖与视图。bridge lifecycle、会话切换、角色管理、聊天交互、图片状态、UI effect 和导航历史已经按 hook 边界分离，新增行为应进入对应 hook/service，而不是重新堆回入口组件。

## 数据流

renderer 发出请求，经 preload/主进程 bridge 到 Python `request_dispatcher.py`；service 调用 owning domain，presenter 将结果转换为共享类型。后端事件沿反方向更新 renderer state。图片等本地资产通过专门的 registry/transport 暴露，不直接把任意文件路径交给视图。

桌宠拖拽不经过 renderer IPC 或 Python bridge：桌宠主体是 Electron 原生拖拽区域，由系统直接移动独立窗口；主进程从窗口移动事件推导左右 running 和 idle 动画、保存位置，并接管右键菜单与原生鼠标双击恢复主窗口。

## 修改影响

- 修改 bridge 请求：同步检查 dispatcher、service、presenter、Electron client 和 renderer 调用方。
- 修改共享类型：检查 Python models/presenter、`desktop/src/shared.ts`、renderer `shared/types.ts`。
- 修改会话切换：检查 bridge 事件优先级、Session cache、聊天消息连续性和导航历史。
- 修改角色 CRUD：复用统一刷新/派生状态流程，避免各页面重复“调用、刷新、同步、导航”。
- 修改桌宠拖拽：同步检查 renderer 原生拖拽区域、窗口原生交互注册与 `DesktopPetController`，并验证窗口位置会保存。
