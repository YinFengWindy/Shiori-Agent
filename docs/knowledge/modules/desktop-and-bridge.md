---
title: 桌面端与桥接
kind: 领域说明
status: 当前有效
last_verified_commit: 3a8ee3a9
source_paths:
  - desktop/src/
  - desktop/renderer/src/
  - desktop_bridge/
  - story_simulation/
related:
  - roles.md
  - conversations-and-sessions.md
  - scheduling.md
  - agent-lifecycle-and-tools.md
  - voice.md
---

# 桌面端与桥接

## 三层结构

- `desktop/src/`：Electron 主进程、窗口、本地资源传输和 Python bridge client。
- `desktop/renderer/src/`：React 界面，包含应用状态装配、聊天、角色、设置、图片和任务页面。
- `desktop_bridge/`：Python 业务边界。`request_dispatcher.py` 负责并发与写入顺序，`request_router.py` 只分发 RPC；role、session/task、chat、image 请求分别进入对应 request handler，再调用 owning service 与 presenter。`DesktopBridgeService` 仅装配依赖、管理生命周期、广播事件并统一映射响应与错误。

`DesktopAppFrame.tsx` 只应装配状态、依赖与视图。bridge lifecycle、会话切换、角色管理、聊天交互、图片状态、UI effect 和导航历史已经按 hook 边界分离，新增行为应进入对应 hook/service，而不是重新堆回入口组件。

桌宠语音的 Electron 主进程控制、隐藏 renderer 采集/播放与 Python provider 协调边界见 [桌宠语音交互](voice.md)。通用 `ipc.ts` 不拥有语音业务，语音 IPC 统一注册在 `desktop/src/voice/ipc.ts`。

## 数据流

renderer 发出请求，经 preload/主进程 bridge 到 Python `request_dispatcher.py`，再由 `DesktopBridgeRequestRouter` 交给单一领域 handler；handler 调用 owning service，presenter 将结果转换为共享类型。后端事件沿反方向更新 renderer state。图片等本地资产通过专门的 registry/transport 暴露，不直接把任意文件路径交给视图。

Story 进入独立路由时才挂载 `StoryRoute`、`useStoryController` 和 `useStoryWorkspacePresentation`；首次读取故事列表的过程直接呈现主菜单加载页，不额外再发起一次主菜单加载。主菜单阶段只有“Read story list”和“Prepare menu”两项，进入已保存剧情时依次使用“Read story”“Restore progress”和“Prepare stage”，不把“Complete”当作额外阶段。加载页的标题、阶段、状态、进度和重试文案统一使用英文。每个真实阶段至少保持 900ms：当前阶段显示旋转箭头，阶段完成后才切到下一阶段并显示勾选；进入 `menu-ready` 或 `opening-ready` 后再短暂停留 420ms，把全部真实阶段显示为勾选，等待阶段保持静止。进入 Story 时会等待开场 `background` 资源完成；后续 Director 在重要视觉节点返回 `visual_prompt` 后异步创建 `cg` 资源，不阻塞已提交剧情。两类资源共用 Story 图片生成链路，完成后都进入 Story visual gallery；舞台优先显示最新完成 CG，没有 CG 时显示开场背景，失败可单独重试且不影响已提交剧情。加载页不提供额外返回入口，错误状态只保留重试操作。阶段仍由真实 bridge 操作推进，而不是用展示层计时器伪造完成状态。

桌宠拖拽不经过 renderer IPC 或 Python bridge：桌宠主体是 Electron 原生拖拽区域，由系统直接移动独立窗口；主进程用窗口移动的左右位移驱动 Codex 图集的 `running-left` / `running-right` 行，在 220ms 静默后回到 `idle`，保存位置，并接管右键菜单与去重后的原生双击恢复主窗口。

角色通过 `pet_action` 操控桌宠时，工具 schema 会按当前回合的角色和渠道动态投影桌宠状态：桌面端角色可看到桌宠开关、当前绑定桌宠包和包声明的动作名及其精灵状态；外部渠道会明确标记为不可用。动作名来自角色素材包的 `actions` 映射，工具执行层仍会再次校验角色绑定、开关、渠道和动作支持情况。

屏幕识别是每个角色默认拥有的 Agent 工具，由核心 runtime 注册，桌面端和 Telegram/QQ 等渠道共用同一能力。`desktop_bridge` 只负责桌面 IPC 的观察分析/记忆接口和环境状态；主屏捕获由 `infra/screen_capture.py` 提供，不读取桌宠绑定配置。Electron 的 `DesktopObservationController` 仍负责桌面端的定时观察、持久化开关和桌宠提示，但不决定 Agent 是否拥有 `observe_screen`。

## 修改影响

- 修改 bridge 请求：同步检查 dispatcher、request router、所属 request handler/service、presenter、Electron client 和 renderer 调用方；不要把领域分支重新加入 `DesktopBridgeService.handle()`。
- 修改共享类型：检查 Python models/presenter、`desktop/src/shared.ts`、renderer `shared/types.ts`。
- 修改会话切换：检查 bridge 事件优先级、Session cache、聊天消息连续性和导航历史。
- 修改角色 CRUD：复用统一刷新/派生状态流程，避免各页面重复“调用、刷新、同步、导航”。
- 修改桌宠拖拽：同步检查 renderer 原生拖拽区域、窗口原生交互注册与 `DesktopPetController`，并验证窗口位置会保存。
- 修改桌宠绑定或托盘开关：同步检查角色素材选择后的 `syncPet()`、主进程持久化状态和托盘菜单刷新。
- 修改屏幕识别：同步检查核心工具注册、角色会话中的 `role_id`、渠道回合、截图获取、模型分析和桌面观察调度；桌面 UI 的暂停状态不能改变角色工具的默认归属。
