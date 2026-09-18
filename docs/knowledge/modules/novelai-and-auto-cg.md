---
title: NovelAI 与自动 CG
kind: 领域说明
status: 当前有效
last_verified_commit: 966af779
source_paths:
  - apps/backend/core/scene/
  - plugins/novelai/
  - plugins/story/
  - apps/backend/agent/plugin_host/
  - apps/desktop/renderer/src/plugins/
  - apps/backend/bus/events_lifecycle.py
related:
  - roles.md
  - conversations-and-sessions.md
  - agent-lifecycle-and-tools.md
---

# NovelAI 与自动 CG

## NovelAI 基础能力

`plugins/novelai/backend/` 拥有设置、请求模型、HTTP 客户端、提示词标签、持久化、`NovelAIService.generate()`、生图工具、自动 CG 与 RPC。`plugins/novelai/ui/` 拥有 Image Studio、提示词标签库与历史界面，经 `nav.page` / `settings.section` 注册页面与设置。

手动 `generate_image` 工具和自动 CG 都应复用该服务，避免各自实现请求与错误处理。生成文件与元数据由插件写入 workspace 下的 `plugin-data/novelai/generation/`；运行数据不应随插件停用或包升级删除。

启停只由宿主管理的 `[plugins.novelai].enabled` 决定，插件配置表单与运行时设置不再声明第二个 `enabled`。插件停用后，宿主撤销工具、RPC 与事件订阅。服务仍检查 Token，角色自动 CG 偏好仍独立生效。

## 插件边界（2026-09-11）

NovelAI 的业务代码、Logo、设置、聊天图片重生成和角色自动 CG 开关均由 `plugins/novelai/` 持有。宿主通过通用角色设置与聊天图片操作扩展位挂载 UI；插件不可用时撤下对应操作。自动 CG 偏好由插件以 `roles/roles.json` 的 `plugin_data.novelai.<role_id>.auto_scene_cg_enabled` 保存；角色表单只修改插件草稿，点击「保存」时和角色字段共同原子提交，取消编辑不落盘。清单 v5 在投影前原子迁出旧 `runtime_config.auto_scene_cg_enabled`，保留 true/false 并以已有命名空间为准，插件停用时的普通角色编辑也不会丢失偏好。停用或清空插件文件不擦除仍存角色的偏好；插件启用及收到角色删除事件时清理已删角色的记录。长耗时 RPC 由插件显式传入 `timeoutMs`，宿主只验证通用截止时间，不识别供应商或生图方法名。

故事模式归于 `plugins/story/`，manifest 显式声明 `dependencies: [novelai]`，通过 `ctx.dependencies.require("novelai")` 获取 NovelAI 导出的 `GenerateImageTool`。故事的模型与提示词策略属于故事插件。宿主没有通用生图接口，也不装配故事业务；故事页面注册为全屏插件导航，RPC 与事件使用 `plugin.story.*` 命名空间。

插件内核按依赖顺序加载、按反向依赖顺序卸载。缺失、禁用或失败的依赖使故事插件进入 `BLOCKED`，其页面和 RPC 不可用；恢复 NovelAI 后重新装配可恢复故事入口。运行时替换先等待旧插件接受的后台任务完成，桥接事件按所属注册表隔离，避免跨代重复转发。首次启用故事时恢复被中断的持久化任务；已有活跃前代时保留其执行权。

素材页的一键生成差分及 `roles.differences.generate` 已移除。已有差分、素材分类和手动心情绑定保持可用。故事数据存于 workspace 的 `plugin-data/story/stories/`，NovelAI 运行数据存于 `plugin-data/novelai/generation/`，启停不删除这些数据。

Story 采用的 CG 和会话消息图片各有独立副本，分别随 Story 与会话内容保留；NovelAI 提示词参考图复制到自身的 `generation/references/`。旧生成目录的 JSONL 记录与元数据路径在迁移后指向新根，并保留旧输出身份用于会话副本的来源查找；请求快照随生成目录迁移。清理 NovelAI 数据不会让 Story 或聊天已有图片消失，但重新生成依赖的原始记录与请求也会被清理。共享 imports 不随 NovelAI 清理，已明确写回角色的素材仍归角色。

Story 播放偏好继续保存在设备 renderer 的 `localStorage["shiori.story-preferences.v1"]`，与工作区故事内容分离；工作区或插件数据目录备份不包含这些偏好。

`_migrate_legacy_novelai_config()` 仍由宿主在加载插件前升级旧配置。共享场景事件、角色存储、会话呈现与资产服务是宿主契约，插件可以复用；本次归位不等同于将全部宿主服务封装为独立 SDK。UI 通过注入的宿主服务访问角色列表、文件选择与事件，不直接使用 Electron 全局对象。

NovelAI 与故事的业务回归分别随 `plugins/novelai/tests/`、`plugins/story/tests/` 保存，前端单测与各自 `ui/` 源文件并列；包括配置往返、依赖启停等通过宿主执行的集成用例。显式安装的 `shiori-plugin-testkit` 提供不含插件业务断言的真实宿主启动 fixture；插件不读取仓库测试树。独立运行流程见 [插件测试](../../agents/plugin-testing.md)。

验收覆盖真实插件配置读写、依赖缺失与循环阻断、NovelAI 启停导致的故事入口/RPC变化、既有数据保留、跨代事件隔离、角色偏好保存及图片重生成的会话归属。

## 自动 CG 生命周期

1. 核心场景服务在 `BeforeTurn` 捕获被动回合上下文，并在 `AfterTurn` 对非空回复调度场景判断；主动消息则从 `ProactiveMessageCommitted` 接入同一判断链。
2. `apps/backend/core/scene/decision.py` 使用独立观察器 system prompt，并强制模型调用内部函数 `submit_scene_observation`，将结果归为 `started`、`same`、`changed`、`closed` 或 `none`。观察结果同时携带持续场景 `scene_key` 与可见定格 `visual_key`。
3. 核心场景服务对函数参数执行协议和语义校验；有效结果才会持久化这两个键并发布 `SceneObservationCommitted`。`scene_key` 供场景追问保持连续性，`visual_key` 供图片生成判断重复。
4. NovelAI 插件通过 `scene_observations` capability 登记角色消费需求，订阅场景事件。`AutoCgController` 独立检查自动 CG 开关、视觉去重、冷却与手动生成抑制；通过后才由 `scene_prompt.py` 使用既有 light 模型把冻结的中立场景事实转换为 NovelAI tags 和画幅，并校验供应商参数。
5. 成功图片通过消息推送发送，并同步回权威角色会话。

`AfterTurnCtx.will_dispatch` 只表示核心消息总线是否还需下发回复，不表示回合是否完成。桌面桥接直接取得回复时该值为 `false`，场景观察仍必须处理这个有效回合。

## 防重复与失败处理

- 自动生成冷却为 5 个用户回合。
- `scene_key` 表示持续场景；`visual_key` 表示当前可见定格。自动 CG 使用 `visual_key` 去重，因此同一场景中的动作、姿势、人物位置关系、构图、服装、道具或光线变化可以生成新的 CG。
- `same` 配合新的 `visual_key` 表示持续场景不变但视觉定格变化；NovelAI 自行在普通 5 回合冷却结束后生成。核心事件不含生图决策、供应商提示词或尺寸。
- 重复定格的策略日志使用 `scene_cg_duplicate_visual`，不再把持续场景本身标记为重复。
- 当前回合若已经调用 `generate_image`，不再追加自动 CG。
- 场景协议无效时，观察器会携带校验原因请求一次修复；控制器不再对同一请求做无反馈重试。
- 修复后仍无效时，不发布场景事件，也不写入场景状态；日志只记录工具调用数量、工具名、参数键和文本长度等响应形态。
- 图片生成保留自身重试；主回复不因后台自动 CG 失败而失败。
- `started` 建立首个场景，`same` 延续当前场景，`changed` 建立新场景，`closed` 关闭场景状态，`none` 表示当前没有可观测场景。
- 可见场景携带 `scene_key`、`visual_key` 和中立自然语言 `visual_description`；事件冻结该回合的角色描述、用户内容和回复，异步提示词模型不会读取之后改变的会话。`closed` 和 `none` 的场景键与视觉描述为空。

## 核心服务所有权与迁移

`[agent.scene_observation].enabled` 控制核心服务，默认开启。角色开启主动且核心 `agent.proactive_strategies.scene_followup` 开启，或至少一个已装配消费者请求时才调用观察模型；仅残留角色自动 CG 偏好但 NovelAI 已停用或卸载，不会形成消费需求。没有 NovelAI 时核心观察和场景跟进照常可用。桌面设置保留显式核心开关，不把缺省值提前写成启用。

候选 runtime 只构造服务，发布时在该代局部事件总线上激活。旧代已接受的回合仍可完成观察，包括发布前捕获、发布后才结束的回合；代际 lease 排空后才退订、取消并等待剩余任务。跨代共享场景 state owner，以同会话观察序号防止较慢旧结果覆盖较新事实。

状态读取优先 `workspace/scene/state.json`。若不存在，读取 `workspace/plugins/scene_awareness/kv.json`，再依次读取新旧插件代码目录的 `.kv.json`；首次真实场景写入原子导入全部旧 key，已存在的新状态始终优先。候选准备不写迁移数据。旧 TOML 停用配置和两处 `plugin.disabled` 在配置加载时幂等转换为核心开关；旧文件不删除。场景插件包已移除，发现和打包仅保留核心模块及实际插件。

## 修改影响

- 修改冷却、`scene_key` 或 `visual_key`：检查状态持久化、重复图片、会话切换、角色隔离和场景追问连续性。
- 修改场景判断输出：同步更新工具 schema、五态迁移、场景/视觉键语义校验和协议修复。
- 修改图片生成：检查手动工具与自动 CG 的共享服务、提示词标签、素材和消息附件格式。
- 修改消息推送：确认渠道收到图片，且 Session/Conversation 中也保留对应消息。

## 验收重点

至少覆盖：无场景结果不落状态、场景开始和切换时生成、同一场景的视觉变化在 5 回合冷却后生成、完全相同定格不重复生成、场景关闭后清理、同回合手动生成抑制、协议反馈修复、协议失败不发事件、生成重试、后台失败不阻塞文本回复、成功图片同步到权威会话。
