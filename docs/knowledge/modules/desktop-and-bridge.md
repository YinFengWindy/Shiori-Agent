---
title: 桌面端与桥接
kind: 领域说明
status: 当前有效
last_verified_commit: 18f56dd4
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

桌宠拖拽不经过 renderer IPC 或 Python bridge：桌宠主体是 Electron 原生拖拽区域，由系统直接移动独立窗口；主进程用窗口移动的左右位移驱动 Codex 图集的 `running-left` / `running-right` 行，在 220ms 静默后回到 `idle`，保存位置，并接管右键菜单与去重后的原生双击恢复主窗口。

屏幕观察由 Electron 主进程中的 `DesktopObservationController` 持有会话、定时器和持久化开关。截图获取失败会立即停止当前会话和调度、持久化关闭观察开关，并向桌宠发布可重试的失败提示；截图成功后的模型或 bridge 临时失败不会撤销开关。Windows 锁屏和桌宠暂时不可用属于暂停，不撤销用户已开启的观察状态。

## 修改影响

- 修改 bridge 请求：同步检查 dispatcher、service、presenter、Electron client 和 renderer 调用方。
- 修改共享类型：检查 Python models/presenter、`desktop/src/shared.ts`、renderer `shared/types.ts`。
- 修改会话切换：检查 bridge 事件优先级、Session cache、聊天消息连续性和导航历史。
- 修改角色 CRUD：复用统一刷新/派生状态流程，避免各页面重复“调用、刷新、同步、导航”。
- 修改桌宠拖拽：同步检查 renderer 原生拖拽区域、窗口原生交互注册与 `DesktopPetController`，并验证窗口位置会保存。
- 修改屏幕观察：区分截图获取、模型分析和环境暂停三类失败，并同步验证 scheduler、持久化开关与桌宠提示状态。
