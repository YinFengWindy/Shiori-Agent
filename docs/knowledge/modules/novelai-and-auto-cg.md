---
title: NovelAI 与自动 CG
kind: 领域说明
status: 当前有效
last_verified_commit: bdfdae59
source_paths:
  - plugins/scene/
  - apps/backend/core/scene/host.py
  - plugins/novelai/
  - plugins/story/
  - apps/backend/agent/plugin_host/
  - apps/desktop/renderer/src/plugins/
  - apps/backend/bus/events_lifecycle.py
  - apps/backend/bootstrap/scene_config_migration.py
  - apps/backend/agent/plugin_host/manifest.py
  - apps/backend/core/roles/migration.py
related:
  - roles.md
  - conversations-and-sessions.md
  - agent-lifecycle-and-tools.md
---

# NovelAI 与自动 CG

## NovelAI 基础能力

`plugins/novelai/backend/` 拥有设置、请求模型、HTTP 客户端、提示词标签、持久化、`NovelAIService.generate()`、生图工具、自动 CG 与 RPC。`plugins/novelai/ui/` 拥有 Image Studio、提示词标签库与历史界面，UI 模块以 `navPage`（含侧栏）注册生图页面、以 `NovelAIConfig` JSON Schema 自动生成设置表单，并通过 `roleSettings`、`chatImageActions` 挂载角色自动 CG 开关与聊天图片重生成。

手动 `generate_image` 工具和自动 CG 都应复用该服务，避免各自实现请求与错误处理。生成文件与元数据由插件写入 workspace 下的 `plugin-data/novelai/generation/`；运行数据不应随插件停用或包升级删除。

启停由宿主管理：`[plugins.novelai].enabled` 的显式值优先，没有显式值时按 manifest 的 `default_enabled: false` 停用。宿主加载配置时不改写开关。新安装的宿主配置模板不预置插件业务配置，业务默认值由 `NovelAIConfig` 提供；可在 设置 › 插件 中启用并配置。插件配置表单与运行时设置不再声明第二个 `enabled`。插件停用后，宿主撤销工具、RPC 与事件订阅。服务仍检查 Token，角色自动 CG 偏好仍独立生效。

## 插件边界（2026-09-11）

NovelAI 的业务代码、Logo、设置、聊天图片重生成和角色自动 CG 开关均由 `plugins/novelai/` 持有。宿主通过通用角色设置与聊天图片操作扩展位挂载 UI；插件不可用时撤下对应操作。自动 CG 偏好由插件以 `roles/roles.json` 的 `plugin_data.novelai.<role_id>.auto_scene_cg_enabled` 保存；角色表单只修改插件草稿，点击「保存」时和角色字段共同原子提交，取消编辑不落盘。角色清单当前版本是 9（`core/roles/migration.py`），加载时要求每条角色已有 `profile` 对象，不再改写 `runtime_config`。停用或清空插件文件不擦除仍存角色的偏好；插件启用及收到角色删除事件时清理已删角色的记录。长耗时 RPC 由插件显式传入 `timeoutMs`，宿主只验证通用截止时间，不识别供应商或生图方法名。

故事模式归于 `plugins/story/`，manifest 显式声明 `dependencies: [novelai]`，通过 `ctx.require(DEPENDENCIES).require("novelai")` 获取 NovelAI 以 `ctx.expose()` 导出的 `ImageGenerationAPI`（`plugins/novelai/backend/api.py` 中的 Protocol，由本代 `GenerateImageTool` 实现），类型不符时故事插件 setup 失败。故事的模型与提示词策略属于故事插件。宿主没有通用生图接口，也不装配故事业务；故事页面注册为全屏插件导航，RPC 与事件使用 `plugin.story.*` 命名空间。

插件内核按依赖顺序加载、按反向依赖顺序卸载。缺失、禁用或失败的依赖使故事插件进入 `BLOCKED`，其页面和 RPC 不可用；恢复 NovelAI 后重新装配可恢复故事入口。运行时替换先等待旧插件接受的后台任务完成，桥接事件按所属注册表隔离，避免跨代重复转发。首次启用故事时恢复被中断的持久化任务；已有活跃前代时保留其执行权。

素材页的一键生成差分及 `roles.differences.generate` 已移除。已有差分、素材分类和手动心情绑定保持可用。故事数据存于 workspace 的 `plugin-data/story/stories/`，NovelAI 运行数据存于 `plugin-data/novelai/generation/`，启停不删除这些数据。

Story 采用的 CG 和会话消息图片各有独立副本，分别随 Story 与会话内容保留；NovelAI 提示词参考图复制到自身的 `generation/references/`。生成记录写在 `plugin-data/novelai/generation/`。清理 NovelAI 数据不会让 Story 或聊天已有图片消失，但重新生成依赖的原始记录与请求也会被清理。共享 imports 不随 NovelAI 清理，已明确写回角色的素材仍归角色。

Story 播放偏好继续保存在设备 renderer 的 `localStorage["shiori.story-preferences.v1"]`，与工作区故事内容分离；工作区或插件数据目录备份不包含这些偏好。

共享场景事件、角色存储、会话呈现与资产服务是宿主契约，插件可以复用；本次归位不等同于将全部宿主服务封装为独立 SDK。UI 通过注入的宿主服务访问角色列表、文件选择与事件，不直接使用 Electron 全局对象。

NovelAI 与故事的业务回归分别随 `plugins/novelai/tests/`、`plugins/story/tests/` 保存，前端单测与各自 `ui/` 源文件并列；包括配置往返、依赖启停等通过宿主执行的集成用例。插件测试使用显式安装的 `shiori-sdk[testing]`；真实宿主启动 fixture 由 `shiori-host-testing` 提供，仅供宿主集成测试使用。插件不读取仓库测试树。独立运行流程见 [插件测试](../../agents/plugin-testing.md)。

验收覆盖真实插件配置读写、依赖缺失与循环阻断、NovelAI 启停导致的故事入口/RPC变化、既有数据保留、跨代事件隔离、角色偏好保存及图片重生成的会话归属。

## 自动 CG 生命周期

1. 系统插件 `plugins/scene` 在代际发布后订阅 `TurnStarting`、`TurnFinished` 和 `ProactiveMessageCommitted`。观察不在回合关键路径上。
2. `plugins/scene/backend/decision.py` 使用独立观察器 system prompt，并强制模型调用内部函数 `submit_scene_observation`，将结果归为 `started`、`same`、`changed`、`closed` 或 `none`。观察结果同时携带持续场景 `scene_key` 与可见定格 `visual_key`。
3. 场景插件对函数参数执行协议和语义校验；有效结果才会持久化这两个键并发布 `SceneObservationCommitted`。`scene_key` 供场景追问保持连续性，`visual_key` 供图片生成判断重复。
4. NovelAI 用 `optional_inject: [scene]` 调用 `SCENE.request`，把返回的释放函数交给 `ctx.effect`。场景插件未启用时不登记需求。`AutoCgController` 独立检查自动 CG 开关、视觉去重、冷却与手动生成抑制；通过后才由 `scene_prompt.py` 使用既有 light 模型把冻结的中立场景事实转换为 NovelAI tags 和画幅，并校验供应商参数。角色能力中的自动场景 CG 卡片通过齿轮弹层编辑中文或多行「补充要求」，独立自动保存至 `plugin_data.novelai.<role_id>.auto_scene_cg_prompt_instructions`；开关仍跟随角色页保存，两种保存只修改各自字段。控制器在调度时读取要求快照，提示词模型将其作为绘图要求理解，空白时不注入；后续编辑影响下一次自动 CG，不改变手动生图、Story 或历史图片的请求重放。删除角色时随该角色的 NovelAI 偏好一同清理。
5. 图片生成成功后立即记录冷却和视觉去重，再执行非主动补发。桌面通过 `message_push`，外部渠道通过 `account_send` 的宿主补发参数，由账号投递服务匹配原始 transport/channel 与 chat ID 对应的当前绑定用户私聊，并同步回权威角色会话；绑定消失或地址变化时明确拒绝，不改发其他用户或会话。

`TurnFinished.will_dispatch` 只表示核心消息总线是否还需下发回复，不表示回合是否完成。桌面桥接直接取得回复时该值为 `false`，场景观察仍必须处理这个有效回合。

## 防重复与失败处理

- 普通自动生成冷却为 5 个用户回合；`started` / `changed` 跳过冷却，但仍执行视觉去重。
- `scene_key` 表示持续场景；`visual_key` 表示当前可见定格。自动 CG 使用 `visual_key` 去重，因此同一场景中的动作、姿势、人物位置关系、构图、服装、道具或光线变化可以生成新的 CG。
- `same` 配合新的 `visual_key` 表示持续场景不变但视觉定格变化；NovelAI 自行在普通 5 回合冷却结束后生成。核心事件不含生图决策、供应商提示词或尺寸。
- 重复定格的策略日志使用 `scene_cg_duplicate_visual`，不再把持续场景本身标记为重复。
- 当前回合若已经调用 `generate_image`，不再追加自动 CG。
- 场景协议无效时，观察器会携带校验原因请求一次修复；控制器不再对同一请求做无反馈重试。
- 修复后仍无效时，不发布场景事件，也不写入场景状态；日志只记录工具调用数量、工具名、参数键和文本长度等响应形态。
- 图片生成保留一次重试；生成失败不记成功冷却。生成成功后的推送异常或取消保留已写入的冷却和视觉去重，避免后续观察再次生图；推送错误照常记录，主回复不因后台自动 CG 失败而失败。
- `started` 建立首个场景，`same` 延续当前场景，`changed` 建立新场景，`closed` 关闭场景状态，`none` 表示当前没有可观测场景。
- 可见场景携带 `scene_key`、`visual_key` 和中立自然语言 `visual_description`；事件冻结该回合的角色描述、用户内容和回复，异步提示词模型不会读取之后改变的会话。`closed` 和 `none` 的场景键与视觉描述为空。

## 场景插件与配置迁移

`[plugins.scene].observation_enabled` 控制场景插件是否观察，缺省为真。旧的 `[agent.scene_observation].enabled` 在 `load_config` 里迁入：插件配置还没有这个键才复制，成功后删掉旧表；插件里已有的值不覆盖；内联表迁不了就抛错且不改文件。角色开启主动且宿主 `agent.proactive_strategies.scene_followup` 为真，或至少一个已装配消费者 `SCENE.request` 时才调用观察模型。没有 NovelAI 时场景观察和场景跟进照常可用。桌面设置把显式开关交给 `scene_observation_enabled`，不把缺省值写进 toml。场景插件经 `SCENE_HOST.on_published` 在本代发布时开始观察，设置页改配置触发的代内重载、以及代内重新启用后立即恢复；NovelAI 随 scene 的代内重载、启用和停用一起重新 setup，启用 scene 后立即登记需求（#949）。

宿主在代际发布时 `activate` 场景服务，排空前 `close`。插件 setup 只构造服务，不在 setup 里订阅。状态文件仍是 `workspace/scene/state.json`。若不存在，首次真实写入从 `workspace/plugins/scene_awareness/kv.json` 和遗留 `.kv.json` 导入；已有新状态优先。

## 修改影响

- 修改冷却、`scene_key` 或 `visual_key`：检查状态持久化、重复图片、会话切换、角色隔离和场景追问连续性。
- 修改场景判断输出：同步更新工具 schema、五态迁移、场景/视觉键语义校验和协议修复。
- 修改图片生成：检查手动工具与自动 CG 的共享服务、提示词标签、素材和消息附件格式。
- 修改消息推送：确认渠道收到图片，且 Session/Conversation 中也保留对应消息。

## 验收重点

至少覆盖：无场景结果不落状态、场景开始和切换时生成、同一场景的视觉变化在 5 回合冷却后生成、完全相同定格不重复生成、场景关闭后清理、同回合手动生成抑制、协议反馈修复、协议失败不发事件、生成重试、后台失败不阻塞文本回复、成功图片同步到权威会话。
