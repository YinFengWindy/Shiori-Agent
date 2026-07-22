---
title: 桌面端与桥接
kind: 领域说明
status: 当前有效
last_verified_commit: 773b21d3
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

桌宠拖拽不经过 Python bridge：桌宠 renderer 的 `pointerdown`/`pointerup` 分别经 preload 发送 `desktop:pet-drag-start`/`desktop:pet-drag-end`。`DesktopPetController` 接到开始命令后以 60Hz 读取系统光标位置并移动独立桌宠窗口；结束时停止跟随并只保存最终位置。不要依赖透明桌宠窗口的原生 `before-mouse-event` 作为拖拽唯一入口。

## 修改影响

- 修改 bridge 请求：同步检查 dispatcher、service、presenter、Electron client 和 renderer 调用方。
- 修改共享类型：检查 Python models/presenter、`desktop/src/shared.ts`、renderer `shared/types.ts`。
- 修改会话切换：检查 bridge 事件优先级、Session cache、聊天消息连续性和导航历史。
- 修改角色 CRUD：复用统一刷新/派生状态流程，避免各页面重复“调用、刷新、同步、导航”。
- 修改桌宠拖拽：同步检查 renderer pointer handlers、`DesktopApi`、preload、`registerDesktopIpc` 与 `DesktopPetController`，并验证拖拽后的最终位置会保存。
