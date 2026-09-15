---
title: 桌面端与桥接
kind: 领域说明
status: 当前有效
last_verified_commit: 9aea4b75
source_paths:
  - apps/desktop/src/
  - apps/desktop/scripts/
  - .github/workflows/windows-release.yml
  - apps/desktop/renderer/src/
  - apps/backend/desktop_bridge/
  - plugins/story/
  - plugins/desktop_pet/
  - plugins/screen_perception/
related:
  - roles.md
  - conversations-and-sessions.md
  - scheduling.md
  - agent-lifecycle-and-tools.md
  - voice.md
---

# 桌面端与桥接

## 三层结构

- `apps/desktop/src/`：Electron 主进程、窗口、本地资源传输和 Python bridge client。
- `apps/desktop/renderer/src/`：React 界面，包含应用状态装配、聊天、角色、设置、图片和任务页面。
- `apps/backend/desktop_bridge/`：Python 业务边界。`request_dispatcher.py` 负责并发与写入顺序，`request_router.py` 只分发 RPC；role、session/task、chat、image 请求分别进入对应 request handler，再调用 owning service 与 presenter。`DesktopBridgeService` 仅装配依赖、管理生命周期、广播事件并统一映射响应与错误。

`DesktopAppFrame.tsx` 只应装配状态、依赖与视图。bridge lifecycle、会话切换、角色管理、聊天交互、图片状态、UI effect 和导航历史已经按 hook 边界分离，新增行为应进入对应 hook/service，而不是重新堆回入口组件。

Windows packaged desktop uses an Electron-builder NSIS bundle with a PyInstaller onedir runtime under `resources/runtime`. The main process resolves packaged resources from `process.resourcesPath`, keeps the workspace and `config.toml` under `%USERPROFILE%\.shiori\workspace`, and starts the sidecar with explicit `bridge`, `--workspace`, and `--config` arguments. Release tags provide the application version and CI emits `SHA256SUMS.txt` alongside the installer; clean Windows installation, upgrade, uninstall, and feature smoke remain release-owner acceptance work.

应用更新由 Electron 主进程的 `DesktopUpdateController` 管理，启动检查与设置中的手动检查共用同一生命周期。安装版自动下载新版本，下载完成后保留系统通知，并可从“设置 → 关于”重启安装；开发模式只显示版本并禁用更新操作。`pnpm dev` 每次启动读取当前提交可追溯的最近一个本地 `v*` 版本 tag，通过 `SHIORI_DEV_VERSION` 传给主进程；没有版本 tag 时使用 `package.json` 版本，不会改写文件。远端新 tag 需先 fetch 到本地并重启 dev。安装包始终使用打包元数据版本。`DesktopApi.updates` 通过独立 IPC 传递带 revision 的状态快照和事件，避免初始读取覆盖更晚的下载事件。关于页不加载后端配置，即使 Python bridge 离线也能显示更新状态。

桌宠语音的 Electron 主进程控制、隐藏 renderer 采集/播放与 Python provider 协调边界见 [桌宠语音交互](voice.md)。通用 `ipc.ts` 不拥有语音业务，语音 IPC 统一注册在 `apps/desktop/src/voice/ipc.ts`。

## 数据流

renderer 发出请求，经 preload/主进程 bridge 到 Python `request_dispatcher.py`，再由 `DesktopBridgeRequestRouter` 交给单一领域 handler；handler 调用 owning service，presenter 将结果转换为共享类型。后端事件沿反方向更新 renderer state。Electron 与 Python bridge 的 JSON-lines stdio 协议固定使用 UTF-8：`DesktopBridgeServer.serve_stdio()` 会在首次读写前重配置 stdin/stdout/stderr，避免 Windows 活动代码页（例如 CP936）在关闭全局 UTF-8 时破坏中文 payload。图片等本地资产通过专门的 registry/transport 暴露，不直接把任意文件路径交给视图。Story 生成的背景和 CG 资源使用资源模型的 `path` 字段进入授权集合，由 preload 缓存转换成 `shiori-asset://` URL 后再渲染；资源文件本身仍由 `LocalAssetRegistry` 和资产协议校验。

Story 插件依赖 NovelAI，进入其全屏插件导航页时才挂载 `StoryPage`、`useStoryController` 和 `useStoryWorkspacePresentation`，业务 RPC 与事件统一经 `plugin.story.*` 分发；首次读取故事列表的过程直接呈现主菜单加载页，不额外再发起一次主菜单加载。主菜单阶段只有“Read story list”和“Prepare menu”两项，进入已保存剧情时依次使用“Read story”“Restore progress”和“Prepare stage”，不把“Complete”当作额外阶段。加载页的标题、阶段、状态、进度和重试文案统一使用英文。每个真实阶段至少保持 900ms：当前阶段显示旋转箭头，阶段完成后才切到下一阶段并显示勾选；进入 `menu-ready` 或 `opening-ready` 后再短暂停留 420ms，把全部真实阶段显示为勾选，等待阶段保持静止。游戏页左上角时间信息右侧同步显示持久化的当前场景中文名。Director 每次提交同时产生持久化的 `current_scene`（稳定 `key`、中文 `name` 与实际在场 `character_ids`），每个 Story 视觉资源保存 `sceneKey`；舞台只接受属于当前场景的资源，场景切换后不会继续显示上一场景 CG。当前场景的 `character` CG 只显示 CG；当前场景的 `scene` CG 在正式角色属于该场景时叠加当前差分立绘；当前场景没有可用 CG 时使用纯黑舞台，不显示菜单默认背景或角色立绘。同一场景已有成功的角色 CG 后，后续自动角色视觉请求不再重复创建资源，继续显示当前角色 CG；只有新的 `scene` 视觉资源才会把舞台切回无角色场景 CG。载入剧情列表在标题下显示持久化的当前故事日期、时间段和中文场景名。Director 和 Story 读模型都会拒绝或兜底非中文场景名，界面不会显示内部英文 key。进入 Story 时会等待开场 `background` 资源完成；后续 Director 在重要视觉节点返回 `visual_prompt` 后异步创建 `cg` 资源，不阻塞已提交剧情。两类资源共用 Story 图片生成链路，完成后都进入 Story visual gallery；失败可单独重试且不影响已提交剧情。CG 重试和重新生成都会先把资源持久化为 `generating` 并广播状态，但保留该资源最近一次成功的 `path`，因此同一场景的当前 CG 会一直显示到新图完成；生成成功后再原地写入新路径，生成失败则保留旧图并持久化错误码。加载页不提供额外返回入口，错误状态只保留重试操作。阶段仍由真实 bridge 操作推进，而不是用展示层计时器伪造完成状态。

桌宠拖拽不经过 renderer IPC 或 Python bridge：桌宠主体是 Electron 原生拖拽区域，由系统直接移动独立窗口；主进程用窗口移动的左右位移驱动 Codex 图集的 `running-left` / `running-right` 行，在 220ms 静默后回到 `idle`，保存位置，并接管右键菜单与去重后的原生双击恢复主窗口。

角色通过 `pet_action` 操控桌宠时，工具 schema 会按当前回合的角色和渠道动态投影桌宠状态：桌面端角色可看到桌宠开关、当前绑定桌宠包和包声明的动作名及其精灵状态；外部渠道会明确标记为不可用。动作名来自角色素材包的 `actions` 映射，工具执行层仍会再次校验角色绑定、开关、渠道和动作支持情况。

角色回复气泡由 `plugins/desktop_pet/background/` 拥有：消费普通聊天和主动消息，按绑定角色过滤，管理五秒计时、锁屏暂停与关闭，并通过通用 surface retained state 保留显示内容。关闭走桌宠自有 `bubble.dismiss` RPC；宿主仅广播 `system.lock-state`，不维护 observation 专用气泡通道。语音状态仍优先覆盖普通回复展示。

按需屏幕识别由「24h视奸插件」（`screen_perception`）提供。截图、只读模型分析与 `observe_screen` 工具均在插件内，使用当前角色身份和视觉模型；停用插件撤销工具及活动分析，桌宠气泡不受影响。旧 observation 分析/记忆 RPC 与无生产调用的记忆写入代码已撤除，持续感知和存储策略留给 #292。`observe` 继续只负责运行遥测。

## 配置生效与任务版本

设置通过 `runtime.apply` 提交 TOML 草稿、预期 generation、操作 ID 和待更新的角色模型绑定。后端先解析和准备候选资源，再使用配置事务记录提交配置及模型绑定，最后发布新的 generation。`runtime.status` 同时返回生效配置文本和 generation，避免读取到不匹配的文件与版本。失败保留旧 runtime 和界面草稿；同一操作 ID 重试不会重复提交。启动前恢复中断的文件事务。

空模型注册是合法启动状态。角色管理、会话浏览和健康检查保持可用；只有实际调用模型的能力返回模型配置错误。显式未绑定角色不会在启动或首次注册模型时被自动补绑。

bridge 连接、会话存储和角色执行锁在进程内保持稳定。聊天、Story、语音、后台子任务、事件后处理及自动图片任务持有开始时的 runtime 引用；旧版本在引用释放后清理。任务列表和取消操作覆盖尚未结束的旧版本。设置应用不会重启 bridge 或重载窗口。

未变的渠道连接复用；同名账号或连接配置替换先暂停新任务进入，等待已接受任务和出站队列完成，再切换连接并提交配置。bridge 在等待期间保持在线，现有任务不会被取消。桌面新任务返回 `runtime_reloading`，不会在客户端报告失败后延迟执行；`runtime.apply` 等待实际提交结果或进程退出，不套用普通请求的 30 秒超时。移除渠道时，旧任务仍可完成已有回复。连接启动或提交失败会恢复旧连接；无法恢复的连接返回降级详情。

Telegram、QQ 和 QQBot 在暂停期间使用有界入站缓冲，复用连接在提交后继续处理。旧账号连接即将关闭或缓冲已满时，通过该原始连接明确提示消息尚未处理、需要重试；不把旧账号消息投给新账号。候选恢复接收与提交之间没有异步让出，提交失败会先重新暂停候选，再回滚连接。

已有向量库的 embedding 模型或维度变更需要显式数据迁移，热更新返回 `memory_storage_incompatible`，不会自动重建或清除向量。凭据、连接地址及兼容的记忆配置可通过新的 runtime 实例生效。

## 修改影响

- 修改 Windows 发版链路：同步检查 `apps/desktop/scripts/`、`.github/workflows/windows-release.yml`、Electron runtime paths、sidecar 启动参数、版本元数据和 checksum 产物；不要把真实 Windows 安装/升级/卸载验收误认为布局校验。

- 修改 bridge 请求：同步检查 dispatcher、request router、所属 request handler/service、presenter、Electron client 和 renderer 调用方；不要把领域分支重新加入 `DesktopBridgeService.handle()`。
- 修改共享类型：检查 Python models/presenter、`apps/desktop/src/bridge/shared.ts`、renderer `shared/types.ts`。
- 修改会话切换：检查 bridge 事件优先级、Session cache、聊天消息连续性和导航历史。
- 修改角色 CRUD：复用统一刷新/派生状态流程，避免各页面重复“调用、刷新、同步、导航”。
- 修改桌宠拖拽：同步检查 renderer 原生拖拽区域、窗口原生交互注册与 `DesktopPetController`，并验证窗口位置会保存。
- 修改桌宠绑定或托盘开关：同步检查角色素材选择后的 `syncPet()`、主进程持久化状态和托盘菜单刷新。
- 修改屏幕识别：检查 `screen_perception` 插件工具注册与卸载、角色会话中的 `role_id`、渠道回合、截图获取和视觉模型选择。桌宠开关与回复状态不决定屏幕工具是否可用。
