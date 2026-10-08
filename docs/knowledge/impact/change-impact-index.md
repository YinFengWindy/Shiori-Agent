---
title: 改动影响索引
kind: 影响分析
status: 当前有效
last_verified_commit: bdfdae59
source_paths:
  - apps/backend/core/
  - apps/backend/agent/
  - apps/backend/bootstrap/runtime/
  - apps/backend/proactive_v2/
  - apps/backend/infra/
  - apps/backend/desktop_bridge/
  - apps/desktop/renderer/src/
  - apps/desktop/src/native/
  - plugins/desktop_pet/background/voice/
  - plugins/desktop_pet/backend/voice_preferences.py
  - packages/sdk/python/shiori_sdk/services.py
  - plugins/sensevoice_asr/
  - plugins/gpt_sovits_tts/
  - scripts/plugin-distribution.mjs
  - scripts/build-plugin.mjs
  - apps/desktop/scripts/runtime-plugin-modules.mjs
  - apps/desktop/scripts/runtime-pyinstaller.mjs
  - packages/sdk/src/hooks/usePrivateDraft.ts
  - packages/sdk/src/hooks/usePrivateAutosave.ts
  - packages/sdk/src/serialDraftQueue.ts
  - packages/sdk/python/shiori_sdk/managed/
  - packages/sdk/src/managed/
related:
  - ../map.md
---

# 改动影响索引

在修改前先用本表确定第一圈影响，再用仓库搜索查调用路径和相关模块，最后打开源码核验。

| 准备修改 | 必查影响面 | 推荐搜索词 |
| --- | --- | --- |
| 角色 schema / CRUD | store、迁移、role_runtime、绑定、Session、关系、任务、桌面共享类型 | `RoleRecord RoleAggregateService RoleRuntimeRegistry` |
| 关系、心情、寂寞 | relationship runtime、Proactive、提示词、场景、桌面展示 | `RoleRelationshipRuntimeService loneliness snapshot` |
| 角色素材 | 资源存储、桌面素材页、提示词、NovelAI、自动 CG | `RoleAssetsPage LocalAssetRegistry NovelAI` |
| 会话键 / 线程 | 渠道标识、Session、Conversation、群聊记忆、桌面缓存 | `session_key SessionManager ConversationService` |
| 消息模型 / 附件 | bus、投影、渠道格式化、桌面 presenter、记忆采样、自动 CG | `InboundMessage OutboundMessage projector media` |
| 记忆 schema / 检索 | SDK 记忆契约、`default_memory` engine、store、索引、过滤、注入、工具、后台写入 | `MemoryEngine MemoryQuery MemoryRuntime MemoryRetrievalPipeline` |
| 上下文预算 / 压缩 | 模型注册 `model_context_window`、输入预算、`CompactionController`、手动 `/compact`、上下文窗口展示、记忆整理 | `CompactionController RequestCompaction build_input_budget model_context_window ContextWindowChanged` |
| 运行时换代 / 设置发布 | CoreRuntime 构建与回滚、引用计数代、任务租约、渠道交接、后台任务交接、关闭顺序 | `GenerationManager RuntimeLease RuntimeDispatcher RuntimeBackground ChannelHost prepare_core_runtime` |
| Proactive 门控 | sensor、presence、关系、state、Agent tick、投递 | `ProactiveLoop AgentTickFactory ProactiveStateStore` |
| Drift | drift state、pipeline、tools、主动互斥、恢复 | `DriftStateStore DriftTurnPipeline` |
| 自动 CG | phase hook、scene decision、cooldown、scene key、NovelAI、消息同步 | `AutoCgController AutoCgPolicy SceneDecision` |
| NovelAI 请求 | settings、store、手动工具、自动 CG、桌面图片面板 | `NovelAIService GenerateImageRequest` |
| Channel 合约 | 所有渠道插件、hub、bootstrap、bus、会话解析、附件 | `Channel ChannelContext supports_stream_events ctx.channels.add` |
| Tool 契约 / 执行 | registry、search、hook、插件、MCP、事件、提示词 | `ToolRegistry ToolExecutor ToolHook McpServerRegistry` |
| 生命周期 phase | 所有 phase module、记忆、插件、自动 CG、观测 | `BeforeTurn AfterTurn PhaseModule` |
| MCP | registry、client pool、工具同步、配置、断线清理 | `McpServerRegistry McpClient ToolRegistry` |
| Bridge API | dispatcher、service、presenter、Electron client、renderer hook | `DesktopBridgeService request_dispatcher DesktopBridgeClient` |
| 桌宠语音 / ASR / TTS | 桌宠 background/voice 输入、轮次匹配与队列，私有 preferences RPC/文件，通用 services，原生设备资源与停用清理 | `PetVoiceController PetVoiceInput PetReplyAudio VoicePreferencesStore PluginServiceRegistry` |
| 本地 ASR / TTS provider | SenseVoice CPU 协议与文件转写，GPT-SoVITS 独立导入身份、跨代 pin/回收、实例租约、未知完成隔离，试听迟到结果，共享 WAV/loopback 工具 | `SenseVoiceClient SynthesisEngine References InstanceState VoiceStore usePreview` |
| 插件分发 / 独立 ZIP | manifest distribution、后端 discovery、三个前端 registry、冻结 runtime staging 与完整 SDK 收集、实际 PyInstaller 参数、公共 builder 与安装信任事务 | `distribution external builtinPluginEntries stageBuiltinPlugins collectSdkRuntimeModules createRuntimePyinstallerArgs buildPlugin` |
| 插件原生音频 / 按键 | src/native 的真实 sender、通信 owner/generation、单次播放与录音校验，surface 自有消息、重载和退出清理 | `PluginNativeSessions bindNativeDocumentLifecycle startCapture cancelCapture` |
| 插件私有角色设置 | roleSettings 卡片 ⚙ 对话框内的插件私有自动保存（GPT-SoVITS 声音：scoped client、真实 roleId、moodCatalog、provider 自有情绪名称和参考） | `PluginRoleSettingsSlot retiredPluginUiContribution GptSoVitsRoleCard ReferenceList` |
| 插件通信处置错误 | pending wait/late admission 的结构化 reason、插件卸载 best-effort 清理和未预期失败反馈；同 code 不等于已处置 | `PluginCommunicationLifetime context_disposed releasePreview` |
| 插件私有文档草稿 | SDK hook 的 client/identity 隔离、读取与保存错误、dirty 上报，两 provider 调用者和宿主 peer ABI | `usePrivateDraft pluginUiPeerExports` |
| 设置自动保存 | SDK 串行草稿队列（宿主设置页、schema 插件配置页与插件私有文档共用）、作用域切换迟到结果、离开时提交、失败暂停与重试，`host.ui.SettingsSavedStatus` 与宿主页角「已保存」一致，SDK 设置页布局组件 | `SerialDraftQueue usePrivateAutosave SettingsSavedStatus SettingsField` |
| 插件托管环境 | SDK 托管运行时（安装位置、按原路径导入、删除、空间预检、子进程与日志解码）、provider 插件调用者、宿主选文件/选目录能力 | `ManagedRuntime Installation OwnedService OwnedChild useManagedRuntime ManagedRuntimePanel` |
| 调度任务 | scheduler、工具、持久化、主动投递、角色删除、桌面表单 | `ScheduleRoleTaskService compute_fire_at` |
| 单角色剧情 | Story repository、Director、角色/玩家快照、bridge 事件、桌面剧情适配层 | `StorySimulationService StoryRepository StorySimulationHandler stories.beat.committed` |

独立 provider、SDK 3.1.2 工具与 SDK 3.1.1 已发布接口迁移见 [语音 Provider 与桌宠交互](../modules/voice.md) 与 [SDK 兼容说明](../../../packages/sdk/README.md#compatibility)。

## 判断顺序

1. 找 owning module，而不是从 UI 或渠道开始补丁。
2. 查写路径、读路径、事件订阅者和持久化边界。
3. 检查角色、会话、渠道三个标识是否仍保持隔离。
4. 检查后台任务、重试、缓存和派生状态是否会重复执行。
5. 只对实际影响范围运行对应测试；跨模块契约变化再扩大回归范围。
