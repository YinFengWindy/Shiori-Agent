---
title: NovelAI 与自动 CG
kind: 领域说明
status: 当前有效
last_verified_commit: 64086699
source_paths:
  - core/integrations/novelai/
  - plugins/scene_awareness/
  - plugins/novelai/
  - bus/events_lifecycle.py
related:
  - roles.md
  - conversations-and-sessions.md
  - agent-lifecycle-and-tools.md
---

# NovelAI 与自动 CG

## NovelAI 基础能力

`core/integrations/novelai/` 拥有设置、请求模型、提示词标签、持久化和 `NovelAIService.generate()`。手动 `generate_image` 工具和自动 CG 都应复用该服务，避免各自实现请求与错误处理。

## 自动 CG 生命周期

1. Scene Awareness 插件在 `BeforeTurn` 捕获被动回合上下文，并在 `AfterTurn` 对非空回复调度场景判断；主动消息则从 `ProactiveMessageCommitted` 接入同一判断链。
2. `plugins/scene_awareness/decision.py` 使用独立观察器 system prompt，并强制模型调用内部函数 `submit_scene_observation`，将结果归为 `started`、`same`、`changed`、`closed` 或 `none`。
3. Scene Awareness 对函数参数执行协议和语义校验；有效结果才会更新场景状态并发布 `SceneObservationCommitted`。
4. NovelAI 插件订阅场景观察事件，`AutoCgController` 根据策略、冷却和去重结果决定是否生成。
5. 成功图片通过消息推送发送，并同步回权威角色会话。

`AfterTurnCtx.will_dispatch` 只表示核心消息总线是否还需下发回复，不表示回合是否完成。桌面桥接直接取得回复时该值为 `false`，场景观察仍必须处理这个有效回合。

## 防重复与失败处理

- 自动生成冷却为 8 个用户回合。
- 使用稳定的 `scene_key` 对同一场景去重。
- 当前回合若已经调用 `generate_image`，不再追加自动 CG。
- 场景协议无效时，观察器会携带校验原因请求一次修复；控制器不再对同一请求做无反馈重试。
- 修复后仍无效时，不发布场景事件，也不写入场景状态；日志只记录工具调用数量、工具名、参数键和文本长度等响应形态。
- 图片生成保留自身重试；主回复不因后台自动 CG 失败而失败。
- `started` 建立首个场景，`same` 延续当前场景，`changed` 建立新场景，`closed` 关闭场景状态，`none` 表示当前没有可观测场景。
- `started` 和 `changed` 必须携带新的稳定 `scene_key` 与完整 CG 参数；`closed` 和 `none` 的场景及图像字段必须为空。

## 修改影响

- 修改冷却或场景 key：检查状态持久化、重复图片、会话切换和角色隔离。
- 修改场景判断输出：同步更新工具 schema、五态迁移、语义校验和协议修复。
- 修改图片生成：检查手动工具与自动 CG 的共享服务、提示词标签、素材和消息附件格式。
- 修改消息推送：确认渠道收到图片，且 Session/Conversation 中也保留对应消息。

## 验收重点

至少覆盖：无场景结果不落状态、场景开始和变化时生成、无变化场景不重复生成、场景关闭后清理、8 回合冷却、同回合手动生成抑制、协议反馈修复、协议失败不发事件、生成重试、后台失败不阻塞文本回复、成功图片同步到权威会话。
